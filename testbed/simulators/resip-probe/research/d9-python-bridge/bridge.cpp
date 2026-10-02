#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <exception>
#include <new>
#include <stdexcept>
#include <thread>
#include <vector>

struct WorkerBatch {
    PyObject* callback = nullptr;
    Py_ssize_t count = 0;
    std::vector<PyObject*> results;
    PyObject* exception_type = nullptr;
    PyObject* exception_value = nullptr;
    PyObject* exception_traceback = nullptr;
};

static bool validate_batch(PyObject* callback, Py_ssize_t count) {
    if (!PyCallable_Check(callback)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable");
        return false;
    }
    if (count < 0) {
        PyErr_SetString(PyExc_ValueError, "count must be non-negative");
        return false;
    }
    return true;
}

static void clear_results(std::vector<PyObject*>& results) {
    for (PyObject*& result : results) {
        Py_XDECREF(result);
        result = nullptr;
    }
}

static PyObject* run_same(PyObject*, PyObject* args) {
    PyObject* callback = nullptr;
    Py_ssize_t count = 0;
    if (!PyArg_ParseTuple(args, "On:run_same", &callback, &count)) {
        return nullptr;
    }
    if (!validate_batch(callback, count)) {
        return nullptr;
    }

    PyObject* results = PyList_New(count);
    if (results == nullptr) {
        return nullptr;
    }

    for (Py_ssize_t event_index = 0; event_index < count; ++event_index) {
        PyObject* event = PyLong_FromSsize_t(event_index);
        if (event == nullptr) {
            Py_DECREF(results);
            return nullptr;
        }
        PyObject* result = PyObject_CallOneArg(callback, event);
        Py_DECREF(event);
        if (result == nullptr) {
            Py_DECREF(results);
            return nullptr;
        }
        PyList_SET_ITEM(results, event_index, result);
    }
    return results;
}

static void invoke_batch_on_native_thread(WorkerBatch* batch) {
    for (Py_ssize_t event_index = 0; event_index < batch->count; ++event_index) {
        PyGILState_STATE gil_state = PyGILState_Ensure();
        PyObject* event = PyLong_FromSsize_t(event_index);
        PyObject* result = event == nullptr
                               ? nullptr
                               : PyObject_CallOneArg(batch->callback, event);
        Py_XDECREF(event);
        if (result == nullptr) {
            if (!PyErr_Occurred()) {
                PyErr_SetString(PyExc_RuntimeError,
                                "callback failed without setting an exception");
            }
            PyErr_Fetch(&batch->exception_type, &batch->exception_value,
                        &batch->exception_traceback);
            clear_results(batch->results);
            PyGILState_Release(gil_state);
            return;
        }
        batch->results[static_cast<std::size_t>(event_index)] = result;
        PyGILState_Release(gil_state);
    }
}

static PyObject* run_worker(PyObject*, PyObject* args) {
    PyObject* callback = nullptr;
    Py_ssize_t count = 0;
    if (!PyArg_ParseTuple(args, "On:run_worker", &callback, &count)) {
        return nullptr;
    }
    if (!validate_batch(callback, count)) {
        return nullptr;
    }

    WorkerBatch batch;
    batch.count = count;
    try {
        batch.results.resize(static_cast<std::size_t>(count), nullptr);
    } catch (const std::length_error&) {
        PyErr_SetString(PyExc_OverflowError, "count is too large");
        return nullptr;
    } catch (const std::bad_alloc&) {
        return PyErr_NoMemory();
    }

    Py_INCREF(callback);
    batch.callback = callback;

    std::thread worker;
    try {
        worker = std::thread(invoke_batch_on_native_thread, &batch);
    } catch (const std::exception& error) {
        Py_DECREF(batch.callback);
        PyErr_SetString(PyExc_RuntimeError, error.what());
        return nullptr;
    }

    PyThreadState* caller_thread_state = PyEval_SaveThread();
    worker.join();
    PyEval_RestoreThread(caller_thread_state);

    Py_DECREF(batch.callback);
    if (batch.exception_type != nullptr) {
        clear_results(batch.results);
        PyErr_Restore(batch.exception_type, batch.exception_value,
                      batch.exception_traceback);
        batch.exception_type = nullptr;
        batch.exception_value = nullptr;
        batch.exception_traceback = nullptr;
        return nullptr;
    }

    PyObject* results = PyList_New(count);
    if (results == nullptr) {
        clear_results(batch.results);
        return nullptr;
    }
    for (Py_ssize_t event_index = 0; event_index < count; ++event_index) {
        const std::size_t result_index = static_cast<std::size_t>(event_index);
        PyList_SET_ITEM(results, event_index, batch.results[result_index]);
        batch.results[result_index] = nullptr;
    }
    return results;
}

static PyMethodDef methods[] = {
    {"run_same", run_same, METH_VARARGS,
     "Call callback with event tokens on the calling thread."},
    {"run_worker", run_worker, METH_VARARGS,
     "Call callback with event tokens from one joined native thread."},
    {nullptr, nullptr, 0, nullptr},
};

static PyModuleDef module_definition = {
    PyModuleDef_HEAD_INIT,
    "as_resip_bridge",
    "Minimal CPython callback bridge experiment.",
    -1,
    methods,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
};

PyMODINIT_FUNC PyInit_as_resip_bridge(void) {
    return PyModule_Create(&module_definition);
}