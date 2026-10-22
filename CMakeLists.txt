cmake_minimum_required(VERSION 3.20)
project(fastmcp_sentinel LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

option(SENTINEL_SANITIZE "Build with AddressSanitizer + UndefinedBehaviorSanitizer" OFF)
option(SENTINEL_BUILD_TESTS "Build native C++ unit tests" ${PROJECT_IS_TOP_LEVEL})

# Target architecture on macOS is controlled by CMAKE_OSX_ARCHITECTURES
# (e.g. -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" for a universal binary).
if(MSVC)
    set(SENTINEL_WARNINGS /W4 /WX)
else()
    set(SENTINEL_WARNINGS -Wall -Wextra -Wpedantic -Wshadow -Werror)
endif()

# Runtime assertions are part of the safety contract (Power of 10, Rule 5):
# keep them enabled even in optimized builds.
string(REPLACE "-DNDEBUG" "" CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE}")
string(REPLACE "/DNDEBUG" "" CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE}")

add_library(sentinel_core SHARED csrc/sentinel_core.cpp)
target_include_directories(sentinel_core PUBLIC csrc)
target_compile_options(sentinel_core PRIVATE ${SENTINEL_WARNINGS})
set_target_properties(sentinel_core PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    PREFIX "lib"
    OUTPUT_NAME "sentinel_core"
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

if(SENTINEL_SANITIZE AND NOT MSVC)
    target_compile_options(sentinel_core PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all)
    target_link_options(sentinel_core PUBLIC -fsanitize=address,undefined)
endif()

if(SKBUILD)
    # Wheel build (scikit-build-core): ship the shared library and the audited
    # C++ sources inside the Python package.
    install(TARGETS sentinel_core
        LIBRARY DESTINATION fastmcp_sentinel
        RUNTIME DESTINATION fastmcp_sentinel
    )
    install(FILES csrc/sentinel_core.cpp csrc/sentinel_core.hpp DESTINATION fastmcp_sentinel/csrc)
elseif(NOT SENTINEL_SANITIZE)
    # Development build: place the library next to its sources where the
    # bridge looks for it when running from a source checkout. Sanitized
    # builds stay in the build tree since they cannot be loaded by Python.
    set_target_properties(sentinel_core PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/csrc"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/csrc"
    )
endif()

if(SENTINEL_BUILD_TESTS AND NOT SKBUILD)
    enable_testing()
    add_executable(sentinel_core_tests tests/native/test_sentinel_core.cpp)
    target_link_libraries(sentinel_core_tests PRIVATE sentinel_core)
    target_compile_options(sentinel_core_tests PRIVATE ${SENTINEL_WARNINGS})
    add_test(NAME sentinel_core_native COMMAND sentinel_core_tests)

    find_program(PYTHON_EXECUTABLE NAMES python3 python)
    if(PYTHON_EXECUTABLE)
        add_custom_target(audit
            COMMAND ${PYTHON_EXECUTABLE} -m fastmcp_sentinel.cli audit --csrc-dir ${CMAKE_CURRENT_SOURCE_DIR}/csrc
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            COMMENT "Running Power of 10 safety invariant audit"
        )
        add_custom_target(run_tests
            COMMAND ${PYTHON_EXECUTABLE} -m pytest tests/
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            DEPENDS sentinel_core
            COMMENT "Running pytest suite"
        )
    endif()
endif()
