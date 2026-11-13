#include "terminal.hpp"
#include <cstdint>
#include <cstdio>
#include <cerrno>
#include <csignal>
#include <iostream>
#include <poll.h>
#include <stdexcept>
#include <termios.h>
#include <unistd.h>

std::string clean(std::string_view text) {
    std::string output;
    auto byte_escape = [&](unsigned char value) {
        char escaped[5];
        std::snprintf(escaped, sizeof(escaped), "\\x%02X", value);
        output += escaped;
    };
    for (size_t i = 0; i < text.size();) {
        const auto lead = static_cast<unsigned char>(text[i]);
        if (lead < 128) {
            output += lead < 32 || lead == 127 ? ' ' : static_cast<char>(lead);
            ++i;
            continue;
        }
        size_t length = lead >= 0xc2 && lead <= 0xdf ? 2 : lead >= 0xe0 && lead <= 0xef ? 3 :
                        lead >= 0xf0 && lead <= 0xf4 ? 4 : 0;
        uint32_t cp = length ? lead & ((1u << (7 - length)) - 1) : 0;
        bool valid = length && i + length <= text.size();
        for (size_t j = 1; valid && j < length; ++j) {
            const auto byte = static_cast<unsigned char>(text[i + j]);
            if ((byte & 0xc0) != 0x80) valid = false;
            else cp = (cp << 6) | (byte & 0x3f);
        }
        if (!valid || (length == 2 && cp < 0x80) || (length == 3 && cp < 0x800) ||
            (length == 4 && cp < 0x10000) || (cp >= 0xd800 && cp <= 0xdfff) || cp > 0x10ffff) {
            byte_escape(lead);
            ++i;
            continue;
        }
        const bool hazardous = (cp >= 0x80 && cp <= 0x9f) || cp == 0x61c || cp == 0x200e || cp == 0x200f ||
                               (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2066 && cp <= 0x2069) ||
                               cp == 0x2028 || cp == 0x2029;
        if (hazardous) {
            char escaped[7];
            std::snprintf(escaped, sizeof(escaped), "\\u%04X", cp);
            output += escaped;
        } else output.append(text.substr(i, length));
        i += length;
    }
    return output;
}

namespace {
// No process-wide handlers: defer termination/suspend signals while the terminal
// is noncanonical, then restore its state before delivering pending signals.
class PromptMode {
    termios original_{};
    sigset_t blocked_{}, original_mask_{};
    bool terminal_saved_ = false, masked_ = false;
public:
    PromptMode() {
        sigemptyset(&blocked_);
        for (int signal : {SIGINT, SIGTERM, SIGHUP, SIGQUIT, SIGTSTP}) sigaddset(&blocked_, signal);
        try {
            if (tcgetattr(STDIN_FILENO, &original_) != 0) throw std::runtime_error("Cannot inspect terminal input mode.");
            terminal_saved_ = true;
            activate();
        } catch (...) { restore(); throw; }
    }
    void activate() {
        if (sigprocmask(SIG_BLOCK, &blocked_, &original_mask_) != 0) throw std::runtime_error("Cannot protect terminal input mode.");
        masked_ = true;
        termios mode = original_;
        mode.c_lflag &= static_cast<tcflag_t>(~(ICANON | ECHO));
        mode.c_cc[VMIN] = 0;
        mode.c_cc[VTIME] = 0;
        if (tcsetattr(STDIN_FILENO, TCSANOW, &mode) != 0) throw std::runtime_error("Cannot enable immediate folder selection.");
    }
    void restore() noexcept {
        if (terminal_saved_) tcsetattr(STDIN_FILENO, TCSANOW, &original_);
        if (masked_) { masked_ = false; sigprocmask(SIG_SETMASK, &original_mask_, nullptr); }
    }
    void deliver_pending() {
        sigset_t pending;
        if (sigpending(&pending) != 0) throw std::runtime_error("Cannot inspect pending terminal signals.");
        for (int signal : {SIGINT, SIGTERM, SIGHUP, SIGQUIT, SIGTSTP}) {
            if (sigismember(&pending, signal) && !sigismember(&original_mask_, signal)) {
                restore(); // Default actions occur with the terminal restored.
                activate(); // Reached after resume, or if a signal handler returns.
                break;
            }
        }
    }
    ~PromptMode() { restore(); }
    PromptMode(const PromptMode&) = delete;
    PromptMode& operator=(const PromptMode&) = delete;
};
}

std::optional<std::string> read_folder_selection() {
    PromptMode mode;
    std::string answer;
    for (;;) {
        mode.deliver_pending();
        pollfd input{STDIN_FILENO, POLLIN, 0};
        int ready = poll(&input, 1, 100);
        if (ready < 0) {
            if (errno == EINTR) continue;
            throw std::runtime_error("Cannot wait for folder selection.");
        }
        if (!ready) continue;
        if (!(input.revents & POLLIN)) {
            if (input.revents & POLLHUP) return std::nullopt;
            throw std::runtime_error("Terminal input is unavailable.");
        }
        unsigned char key = 0;
        ssize_t count = read(STDIN_FILENO, &key, 1);
        if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (count < 0) throw std::runtime_error("Cannot read folder selection.");
        if (!count) { if (input.revents & POLLHUP) return std::nullopt; continue; }
        if (key == 'q' || key == 'Q' || key == 4) {
            std::cout << (key == 4 ? "\n" : std::string(1, static_cast<char>(key)) + "\n") << std::flush;
            return std::nullopt;
        }
        if (key == '\n' || key == '\r') { std::cout << '\n' << std::flush; return answer; }
        if (key == 8 || key == 127) {
            if (!answer.empty()) { answer.pop_back(); std::cout << "\b \b" << std::flush; }
        } else if (key >= 32 && key < 127 && answer.size() < 64) {
            answer += static_cast<char>(key);
            std::cout << static_cast<char>(key) << std::flush;
        }
    }
}
