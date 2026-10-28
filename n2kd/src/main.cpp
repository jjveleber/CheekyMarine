#include <cstring>
#include <iostream>

#include "n2k/Version.h"

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--version") == 0) {
        std::cout << "n2kd " << n2k::version() << "\n";
        return 0;
    }
    std::cerr << "usage: n2kd [--version]\n";
    return 2;
}
