configure_file(include/n2k/Version.h.in ${CMAKE_CURRENT_BINARY_DIR}/include/n2k/Version.h)

add_library(n2kcore STATIC src/Version.cpp src/Frame.cpp src/LogFileSource.cpp src/SocketCanSource.cpp src/FastPacket.cpp)
target_include_directories(n2kcore PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_BINARY_DIR}/include)
target_link_libraries(n2kcore PUBLIC nlohmann_json::nlohmann_json)

add_executable(n2kd src/main.cpp)
target_link_libraries(n2kd PRIVATE n2kcore)

add_executable(n2kd_tests tests/test_version.cpp tests/test_frame.cpp tests/test_logfilesource.cpp tests/test_socketcan.cpp tests/test_fastpacket.cpp)
target_link_libraries(n2kd_tests PRIVATE n2kcore Catch2::Catch2WithMain)

include(Catch)
catch_discover_tests(n2kd_tests)
