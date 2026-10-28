include(GNUInstallDirs)

configure_file(include/n2k/Version.h.in ${CMAKE_CURRENT_BINARY_DIR}/include/n2k/Version.h)
configure_file(systemd/n2kd.service.in ${CMAKE_CURRENT_BINARY_DIR}/n2kd.service @ONLY)

add_library(n2kcore STATIC src/Version.cpp src/Frame.cpp src/LogFileSource.cpp src/SocketCanSource.cpp src/FastPacket.cpp src/PgnDatabase.cpp src/PgnDecoder.cpp src/AisTargets.cpp src/StateMappers.cpp src/Json.cpp src/Publisher.cpp src/RawLogger.cpp src/AddressClaim.cpp src/Daemon.cpp)
target_include_directories(n2kcore PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_BINARY_DIR}/include)
target_link_libraries(n2kcore PUBLIC nlohmann_json::nlohmann_json)

add_executable(n2kd src/main.cpp)
target_link_libraries(n2kd PRIVATE n2kcore)
target_compile_definitions(n2kd PRIVATE
    N2K_CANBOAT_JSON_INSTALLED="${CMAKE_INSTALL_FULL_DATADIR}/cheekymarine/canboat.json")
if(N2K_SOURCE_PGNS_FALLBACK)
    target_compile_definitions(n2kd PRIVATE N2K_CANBOAT_JSON="${PROJECT_SOURCE_DIR}/third_party/canboat/canboat.json")
endif()

if(N2K_BUILD_TESTS)
    add_executable(n2kd_tests tests/test_version.cpp tests/test_frame.cpp tests/test_logfilesource.cpp tests/test_socketcan.cpp tests/test_fastpacket.cpp tests/test_pgndecoder.cpp tests/test_state.cpp tests/test_mappers.cpp tests/test_json.cpp tests/test_publisher.cpp tests/test_rawlogger.cpp tests/test_addressclaim.cpp tests/test_daemon.cpp)
    target_compile_definitions(n2kd_tests PRIVATE N2K_CANBOAT_JSON="${PROJECT_SOURCE_DIR}/third_party/canboat/canboat.json"
        N2KD_BINARY="$<TARGET_FILE:n2kd>" N2K_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures"
        N2K_EXPECTED_VERSION="${PROJECT_VERSION}")
    target_link_libraries(n2kd_tests PRIVATE n2kcore Catch2::Catch2WithMain)
    add_dependencies(n2kd_tests n2kd)

    include(Catch)
    catch_discover_tests(n2kd_tests)
endif()

install(FILES ${PROJECT_SOURCE_DIR}/third_party/canboat/canboat.json DESTINATION ${CMAKE_INSTALL_DATADIR}/cheekymarine)
install(TARGETS n2kd)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/n2kd.service DESTINATION lib/systemd/system)
install(FILES systemd/cheekymarine.sysusers DESTINATION lib/sysusers.d RENAME cheekymarine.conf)
