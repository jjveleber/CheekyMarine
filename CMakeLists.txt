cmake_minimum_required(VERSION 3.25)
project(CheekyMarine VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(N2K_BUILD_TESTS "Build the unit tests (fetches Catch2)" ON)

include(cmake/Dependencies.cmake)

# Added after dependencies so warnings-as-errors only affect our own targets.
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-Wall -Wextra -Werror)
endif()

if(N2K_BUILD_TESTS)
    enable_testing()
endif()
add_subdirectory(n2kd)
