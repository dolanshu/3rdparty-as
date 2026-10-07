# M8 native 一致性 runbook（一句话）

签收跑前必须先构建与被测证据对应的 native 扩展：`make m2-platform-resip-build`，行使 two-leg / recovery 证据时另加 `make m7-platform-two-leg-build` / `make m7-platform-recovery-build`；随后运行计划 §7 命令：`AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py -m contract -q` 与 `AS_REQUIRE_NATIVE_EXTENSIONS=1 uv run pytest platform/tests/test_m7_forward_two_leg_integration.py platform/tests/test_req_f4_sdp_identity_integration.py -m integration -q`（缺扩展即 fail 而非 skip）。
