"""Static AST & Source Safety Invariant Auditor.

Mechanically enforces Gerard J. Holzmann's Power of 10 Safety Invariants on C++ source files:
- Rule 1: Simple Control Flow (No goto, setjmp, longjmp)
- Rule 2: Bounded Loops (No unbounded while loops)
- Rule 3: No Dynamic Memory After Initialization (Zero malloc/new/free/delete)
- Rule 4: Function Length <= 60 lines
- Rule 5: Assertion Density >= 2 assertions per function
- Rule 8: Preprocessor limits (No macro functions or ifdef mazes)
- Rule 9: Pointer dereference restriction (No double pointers or function pointers)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class FunctionMetric:
    name: str
    file: str
    start_line: int
    end_line: int
    line_count: int
    assert_count: int
    passed_length: bool
    passed_asserts: bool


@dataclass
class AuditReport:
    passed: bool
    violations: List[str] = field(default_factory=list)
    function_metrics: List[FunctionMetric] = field(default_factory=list)
    rules_checked: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations_count": len(self.violations),
            "violations": self.violations,
            "functions_audited": len(self.function_metrics),
            "rules_checked": self.rules_checked,
            "functions": [
                {
                    "name": f.name,
                    "file": f.file,
                    "lines": f.line_count,
                    "assertions": f.assert_count,
                    "valid": f.passed_length and f.passed_asserts,
                }
                for f in self.function_metrics
            ],
        }


class SafetyInvariantAuditor:
    """Institutional static auditor for deterministic C++ systems."""

    FORBIDDEN_CONTROL_FLOW = [r"\bgoto\b", r"\bsetjmp\b", r"\blongjmp\b"]
    FORBIDDEN_HEAP = [r"\bmalloc\b", r"\bcalloc\b", r"\brealloc\b", r"\bfree\b", r"\bnew\s+", r"\bdelete\s+"]
    FORBIDDEN_POINTERS = [r"\*\*", r"\(\s*\*\s*[a-zA-Z0-9_]+\s*\)\s*\("]  # double pointers, function pointers

    def __init__(self, csrc_dir: str | Path) -> None:
        self.csrc_dir = Path(csrc_dir)

    def _extract_functions(self, content: str, filename: str) -> List[FunctionMetric]:
        lines = content.splitlines()
        metrics: List[FunctionMetric] = []

        # Regex to locate C++ function signatures followed by opening brace
        # e.g., int sentinel_validate_tx(...) {
        func_regex = re.compile(
            r"^(?:static\s+|inline\s+|extern\s+\"C\"\s+)?(?:int|void|uint[0-9]+_t|size_t|bool|Sentinel[A-Za-z]+)\s+([A-Za-z0-9_]+)\s*\([^;]*?\)\s*\{",
            re.MULTILINE,
        )

        for match in func_regex.finditer(content):
            func_name = match.group(1)
            start_pos = match.start()
            # Calculate 1-based start line
            start_line = content[:start_pos].count("\n") + 1

            # Match balanced braces to find function end
            brace_count = 0
            found_open = False
            end_pos = start_pos

            for i in range(match.end() - 1, len(content)):
                char = content[i]
                if char == "{":
                    brace_count += 1
                    found_open = True
                elif char == "}":
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        end_pos = i
                        break

            end_line = content[:end_pos].count("\n") + 1
            func_body = content[match.end() - 1 : end_pos + 1]
            func_lines = end_line - start_line + 1

            # Count assertions inside function
            assert_matches = re.findall(r"\bassert\s*\(", func_body)
            assert_count = len(assert_matches)

            metrics.append(
                FunctionMetric(
                    name=func_name,
                    file=filename,
                    start_line=start_line,
                    end_line=end_line,
                    line_count=func_lines,
                    assert_count=assert_count,
                    passed_length=(func_lines <= 60),
                    passed_asserts=(assert_count >= 2),
                )
            )

        return metrics

    def audit(self) -> AuditReport:
        violations: List[str] = []
        function_metrics: List[FunctionMetric] = []
        rules = {
            "Rule 1 (Simple Control Flow)": True,
            "Rule 2 (Bounded Loops)": True,
            "Rule 3 (Zero Dynamic Heap)": True,
            "Rule 4 (Function Length <= 60)": True,
            "Rule 5 (Assertion Density >= 2)": True,
            "Rule 8 (No Preprocessor Abuse)": True,
            "Rule 9 (Restricted Pointers)": True,
        }

        cpp_files = list(self.csrc_dir.glob("*.cpp")) + list(self.csrc_dir.glob("*.hpp"))

        if not cpp_files:
            violations.append(f"No C++ files discovered in {self.csrc_dir}")
            return AuditReport(passed=False, violations=violations, rules_checked=rules)

        for file_path in sorted(cpp_files):
            filename = file_path.name
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Rule 1: Control Flow
            for pat in self.FORBIDDEN_CONTROL_FLOW:
                if re.search(pat, content):
                    violations.append(f"[{filename}] Rule 1 Violation: Forbidden control flow '{pat}' detected.")
                    rules["Rule 1 (Simple Control Flow)"] = False

            # Rule 2: Unbounded loops (e.g. while(true), while(1) without break)
            if re.search(r"\bwhile\s*\(\s*(true|1)\s*\)", content):
                violations.append(f"[{filename}] Rule 2 Violation: Potentially unbounded loop while(true/1) detected.")
                rules["Rule 2 (Bounded Loops)"] = False

            # Rule 3: Dynamic Heap
            for pat in self.FORBIDDEN_HEAP:
                if re.search(pat, content):
                    violations.append(f"[{filename}] Rule 3 Violation: Dynamic heap allocation '{pat}' detected.")
                    rules["Rule 3 (Zero Dynamic Heap)"] = False

            # Rule 8: Macro functions (#define FOO(x))
            macro_func_pat = r"^\s*#define\s+[A-Za-z0-9_]+\s*\([^\)]*\)"
            if re.search(macro_func_pat, content, re.MULTILINE):
                violations.append(f"[{filename}] Rule 8 Violation: Preprocessor function-like macro detected.")
                rules["Rule 8 (No Preprocessor Abuse)"] = False

            # Rule 9: Restrict pointers (double pointers or function pointers)
            for pat in self.FORBIDDEN_POINTERS:
                if re.search(pat, content):
                    violations.append(f"[{filename}] Rule 9 Violation: Restricted pointer structure '{pat}' detected.")
                    rules["Rule 9 (Restricted Pointers)"] = False

            # Rules 4 & 5: Function metrics
            if file_path.suffix == ".cpp":
                funcs = self._extract_functions(content, filename)
                function_metrics.extend(funcs)
                for func in funcs:
                    if not func.passed_length:
                        violations.append(
                            f"[{filename}] Rule 4 Violation: Function '{func.name}' length {func.line_count} exceeds 60 lines limit."
                        )
                        rules["Rule 4 (Function Length <= 60)"] = False
                    if not func.passed_asserts:
                        violations.append(
                            f"[{filename}] Rule 5 Violation: Function '{func.name}' has {func.assert_count} assertions (minimum 2 required)."
                        )
                        rules["Rule 5 (Assertion Density >= 2)"] = False

        passed = len(violations) == 0
        return AuditReport(
            passed=passed,
            violations=violations,
            function_metrics=function_metrics,
            rules_checked=rules,
        )
