#include "process.hpp"
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <stdexcept>
#include <fcntl.h>
#include <poll.h>
#include <sys/wait.h>
#include <unistd.h>

// All child input travels through a pipe. Never invoke a shell or expose secrets in argv.
ProcessResult process(const std::vector<std::string>& args, const std::string& input,
                      size_t limit, int seconds) {
    int in[2], out[2];
    if (pipe(in) != 0) throw std::runtime_error("Cannot create process pipe.");
    if (pipe(out) != 0) { close(in[0]); close(in[1]); throw std::runtime_error("Cannot create process pipe."); }
    pid_t pid = fork();
    if (pid < 0) {
        for (int fd : {in[0], in[1], out[0], out[1]}) close(fd);
        throw std::runtime_error("Cannot start child process.");
    }
    if (pid == 0) {
        dup2(in[0], STDIN_FILENO); dup2(out[1], STDOUT_FILENO);
        int nullfd = open("/dev/null", O_WRONLY);
        if (nullfd >= 0) { dup2(nullfd, STDERR_FILENO); close(nullfd); }
        for (int fd : {in[0], in[1], out[0], out[1]}) close(fd);
        std::vector<char*> argv;
        for (const auto& arg : args) argv.push_back(const_cast<char*>(arg.c_str()));
        argv.push_back(nullptr);
        execvp(argv[0], argv.data());
        _exit(127);
    }
    close(in[0]); close(out[1]);
    fcntl(in[1], F_SETFL, O_NONBLOCK); fcntl(out[0], F_SETFL, O_NONBLOCK);
    size_t sent = 0; std::string output; bool limited = false, timeout = false;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    if (input.empty()) { close(in[1]); in[1] = -1; }
    while (out[0] >= 0 || in[1] >= 0) {
        if (std::chrono::steady_clock::now() >= deadline) { timeout = true; break; }
        pollfd fds[2]{{out[0], POLLIN, 0}, {in[1], POLLOUT, 0}};
        int ready = poll(fds, 2, 100);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0) { timeout = true; break; }
        if (in[1] >= 0 && (fds[1].revents & POLLOUT)) {
            ssize_t count = write(in[1], input.data() + sent, input.size() - sent);
            if (count > 0) sent += static_cast<size_t>(count);
            if (sent == input.size() || (count < 0 && errno != EAGAIN && errno != EINTR)) {
                close(in[1]); in[1] = -1;
            }
        }
        if (in[1] >= 0 && (fds[1].revents & (POLLERR | POLLHUP))) { close(in[1]); in[1] = -1; }
        if (out[0] >= 0 && (fds[0].revents & (POLLIN | POLLHUP | POLLERR))) {
            char buf[8192]; ssize_t count = read(out[0], buf, sizeof(buf));
            if (count > 0) {
                size_t take = std::min(static_cast<size_t>(count), limit - output.size());
                output.append(buf, take);
                if (take != static_cast<size_t>(count)) { limited = true; break; }
            } else if (count == 0 || (errno != EAGAIN && errno != EINTR)) { close(out[0]); out[0] = -1; }
        }
    }
    if (timeout || limited) kill(pid, SIGKILL);
    if (in[1] >= 0) close(in[1]);
    if (out[0] >= 0) close(out[0]);
    int status = 0;
    bool reaped = false;
    while (!timeout && !limited) {
        pid_t result = waitpid(pid, &status, WNOHANG);
        if (result == pid) { reaped = true; break; }
        if (result < 0) {
            if (errno == EINTR) continue;
            throw std::runtime_error("Cannot collect child process status.");
        }
        if (std::chrono::steady_clock::now() >= deadline) {
            timeout = true;
            kill(pid, SIGKILL);
            break;
        }
        poll(nullptr, 0, 20);
    }
    if (!reaped) while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
    if (timeout) throw std::runtime_error("Child process timed out.");
    return {WIFEXITED(status) ? WEXITSTATUS(status) : 128, std::move(output), limited};
}
