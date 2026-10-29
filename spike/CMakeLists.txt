# Throwaway MapLibre spike (plan 3, Task 1). Deleted at the end of the task.
cmake_minimum_required(VERSION 3.21)
project(mlnspike LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Quick OpenGL)
find_package(QMapLibre REQUIRED COMPONENTS Core)

qt_add_executable(mlnspike main.cpp mapitem.cpp mapitem.h)
target_link_libraries(mlnspike PRIVATE Qt6::Quick Qt6::OpenGL QMapLibre::Core)
