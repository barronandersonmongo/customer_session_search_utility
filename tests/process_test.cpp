#include "process.hpp"
#include <cerrno>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <unistd.h>

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "sigpipe-default") {
        struct sigaction disposition{};
        return sigaction(SIGPIPE, nullptr, &disposition) == 0 && disposition.sa_handler == SIG_DFL ? 0 : 1;
    }
    std::signal(SIGPIPE, SIG_IGN);
    if (argc == 2) {
        const std::string mode = argv[1];
        if (mode == "close-stdout") { close(STDOUT_FILENO); sleep(10); return 0; }
        if (mode == "hold-stdout") { std::cout << "partial\n" << std::flush; sleep(10); return 0; }
        if (mode == "echo") { std::cout << std::cin.rdbuf(); return 0; }
        return 2;
    }
    try {
        const auto self = std::filesystem::canonical(argv[0]).string();
        require(process({self, "sigpipe-default"}, "", 1024, 1).code == 0, "Child inherited ignored SIGPIPE.");
        struct sigaction disposition{};
        require(sigaction(SIGPIPE, nullptr, &disposition) == 0 && disposition.sa_handler == SIG_IGN,
                "Parent SIGPIPE disposition changed.");
        for (const auto& mode : {"close-stdout", "hold-stdout"}) {
            auto start = std::chrono::steady_clock::now();
            auto result = process({self, mode}, "", 1024, 1);
            require(result.timed_out, "Overdue child did not time out.");
            if (std::string(mode) == "hold-stdout") require(result.output == "partial\n", "Timeout discarded partial output.");
            require(std::chrono::steady_clock::now() - start < std::chrono::seconds(3), "Deadline was exceeded.");
            int status;
            require(waitpid(-1, &status, WNOHANG) == -1 && errno == ECHILD, "Child was not reaped.");
        }
        const std::string payload(256 * 1024, 'x');
        auto echo = process({self, "echo"}, payload, payload.size() + 1, 2);
        require(echo.code == 0 && echo.output == payload && !echo.limited, "Pipe exchange failed.");
        auto limited = process({self, "echo"}, payload, 64, 2);
        require(limited.limited && limited.output.size() == 64, "Output cap failed.");
        std::cout << "Process deadlines, reaping, pipe exchange, and output caps passed.\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
