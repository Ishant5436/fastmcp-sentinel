cmake_minimum_required(VERSION 3.20)
project(fastmcp_sentinel LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Compiler warnings and optimization flags
if(MSVC)
    add_compile_options(/W4 /WX /O2)
else()
    add_compile_options(-O3 -Wall -Wextra -Werror -fPIC)
    if(APPLE)
        add_compile_options(-arch arm64)
    endif()
endif()

# Shared library target
add_library(sentinel_core SHARED
    csrc/sentinel_core.cpp
    csrc/sentinel_core.hpp
)

set_target_properties(sentinel_core PROPERTIES
    PREFIX "lib"
    OUTPUT_NAME "sentinel_core"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/csrc"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/csrc"
)

# Custom test and audit targets
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/venv/bin/python")
    set(PYTHON_EXECUTABLE "${CMAKE_CURRENT_SOURCE_DIR}/venv/bin/python")
else()
    find_program(PYTHON_EXECUTABLE NAMES python3 python)
endif()

if(PYTHON_EXECUTABLE)
    add_custom_target(audit
        COMMAND ${CMAKE_COMMAND} -E env PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/src ${PYTHON_EXECUTABLE} scripts/audit_safety_invariants.py
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        COMMENT "Running Power of 10 Safety Invariants AST Audit"
    )

    add_custom_target(run_tests
        COMMAND ${CMAKE_COMMAND} -E env PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/src ${PYTHON_EXECUTABLE} -m pytest tests/ -v
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        DEPENDS sentinel_core
        COMMENT "Running Pytest test suite"
    )
endif()
