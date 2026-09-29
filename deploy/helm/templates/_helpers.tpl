{{/*
Naming and label helpers for the 3rdparty-as chart.

One use case = one process = one Deployment (ADR-0002), so every per-use-case
object carries the `app.kubernetes.io/use-case` label and is named
`<fullname>-<useCase>`.

The per-use-case helpers take a dict context:
  include "as.useCaseLabels" (dict "Release" $.Release "Chart" $.Chart
                                  "Values" $.Values "useCase" $uc.name)
*/}}

{{/* Chart name, overridable, DNS-safe. */}}
{{- define "as.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified object name prefix. */}}
{{- define "as.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* "<chart>-<version>" for the helm.sh/chart label. */}}
{{- define "as.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Namespace: one namespace holds one complete system (REQ-NF-9). */}}
{{- define "as.namespace" -}}
{{- default .Release.Namespace .Values.namespace -}}
{{- end -}}

{{/* Image reference; an empty tag falls back to Chart.appVersion. */}}
{{- define "as.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) -}}
{{- end -}}

{{/* Selector labels, shared by every object of the release. */}}
{{- define "as.selectorLabels" -}}
app.kubernetes.io/name: {{ include "as.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Full label set, shared by every object of the release. */}}
{{- define "as.labels" -}}
helm.sh/chart: {{ include "as.chart" . }}
{{ include "as.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: 3rdparty-as
{{- end -}}

{{/* Selector labels of one use case. Requires a dict with "useCase". */}}
{{- define "as.useCaseSelectorLabels" -}}
app.kubernetes.io/name: {{ include "as.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/use-case: {{ .useCase }}
{{- end -}}

{{/* Full label set of one use case. Requires a dict with "useCase". */}}
{{- define "as.useCaseLabels" -}}
helm.sh/chart: {{ include "as.chart" . }}
{{ include "as.useCaseSelectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: 3rdparty-as
{{- end -}}

{{/*
Name of the Secret holding the PostgreSQL credentials: the customer-managed one
when postgres.secretName is set, otherwise the chart-managed placeholder Secret.
*/}}
{{- define "as.postgresSecretName" -}}
{{- default (printf "%s-credentials" (include "as.fullname" .)) .Values.postgres.secretName -}}
{{- end -}}
