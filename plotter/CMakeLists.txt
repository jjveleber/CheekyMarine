cmake_minimum_required(VERSION 3.25)

# The app's semver, independent of the root project's (n2kd) version.
set(PLOTTER_VERSION 0.1.0)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Network Sql Quick QuickControls2 Test QuickTest)
qt_standard_project_setup(REQUIRES 6.5)
qt_policy(SET QTP0004 NEW)
find_package(QMapLibre REQUIRED COMPONENTS Core)

configure_file(src/core/Version.h.in ${CMAKE_CURRENT_BINARY_DIR}/generated/plotter/Version.h @ONLY)

# All application logic lives here so tests can link it.
add_library(plottercore STATIC
    src/core/Placeholder.cpp
    src/core/N2kParse.cpp
    src/core/N2kClient.cpp
    src/core/VesselModel.cpp
    src/core/AisModel.cpp
    src/core/Fields.cpp
    src/core/Store.cpp
    src/core/Settings.cpp
    src/core/PackCatalog.cpp
    src/core/StyleLoader.cpp
    src/core/DepthFilters.cpp
    src/core/Geo.cpp
    src/core/Overlays.cpp
    src/core/ChartMap.h
    src/core/ChartController.cpp)
set_target_properties(plottercore PROPERTIES AUTOMOC ON)
target_include_directories(plottercore PUBLIC
    ${CMAKE_CURRENT_BINARY_DIR}/generated
    ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(plottercore PUBLIC Qt6::Core Qt6::Gui Qt6::Network Qt6::Sql)

# plotter_add_test(NAME SOURCES...): Qt Test executable linked to plottercore, run by ctest.
function(plotter_add_test name)
    add_executable(${name} ${ARGN})
    target_link_libraries(${name} PRIVATE plottercore Qt6::Test)
    target_compile_definitions(${name} PRIVATE
        PLOTTER_FIXTURES="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures"
        PLOTTER_EXPECTED_VERSION="${PLOTTER_VERSION}")
    set_target_properties(${name} PROPERTIES AUTOMOC ON)
    add_test(NAME ${name} COMMAND ${name})
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

plotter_add_test(tst_version tests/tst_version.cpp)
plotter_add_test(tst_n2kparse tests/tst_n2kparse.cpp)
plotter_add_test(tst_n2kclient tests/tst_n2kclient.cpp)
plotter_add_test(tst_fields tests/tst_fields.cpp)
plotter_add_test(tst_store tests/tst_store.cpp)
plotter_add_test(tst_settings tests/tst_settings.cpp)
plotter_add_test(tst_packcatalog tests/tst_packcatalog.cpp)
plotter_add_test(tst_styleloader tests/tst_styleloader.cpp)
plotter_add_test(tst_depthfilters tests/tst_depthfilters.cpp)
plotter_add_test(tst_geo tests/tst_geo.cpp)
plotter_add_test(tst_overlays tests/tst_overlays.cpp)
plotter_add_test(tst_chartcontroller tests/tst_chartcontroller.cpp)

# Linking Qt6::Sql and QMapLibre directly puts Qt's lib dir and the QMapLibre lib dir in the
# automatic build RPATH, so libQMapLibre.so resolves libQt6Sql without LD_LIBRARY_PATH.
qt_add_executable(cheekyplotter src/app/main.cpp src/app/MapLibreChartMap.cpp src/app/Icons.cpp)
qt_add_qml_module(cheekyplotter
    URI CheekyMarine
    VERSION 1.0
    QML_FILES qml/Main.qml qml/ChartPage.qml)
target_link_libraries(cheekyplotter PRIVATE plottercore Qt6::Quick Qt6::QuickControls2 Qt6::Sql QMapLibre::Core)
set_target_properties(cheekyplotter PROPERTIES AUTOMOC ON)
# The linker drops Qt6::Sql (nothing in the app uses it directly) and RUNPATH is not searched for the
# dependencies of libQMapLibre.so, so emit a classic RPATH, which is.
target_link_options(cheekyplotter PRIVATE -Wl,--disable-new-dtags)

# Synthetic N2K generator test: replays the generated scenario through the real n2kd.
if(TARGET n2kd)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_test(NAME synth_n2k COMMAND ${Python3_EXECUTABLE} -I ${CMAKE_CURRENT_SOURCE_DIR}/tools/test_synth_n2k.py)
    set_tests_properties(synth_n2k PROPERTIES ENVIRONMENT "N2KD=$<TARGET_FILE:n2kd>")
endif()
