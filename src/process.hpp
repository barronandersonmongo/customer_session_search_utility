#pragma once
#include <string>
#include <vector>

struct ProcessResult { int code; std::string output; bool limited; bool timed_out; };
ProcessResult process(const std::vector<std::string>& args, const std::string& input,
                      size_t limit, int seconds);
