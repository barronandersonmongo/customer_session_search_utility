#pragma once
#include <string>
#include <vector>
#include <functional>

struct ProcessResult { int code; std::string output; bool limited; bool timed_out; };
enum class ChildEnvironment { Inherited, Curl };
ProcessResult process(const std::vector<std::string>& args, const std::string& input,
                      size_t limit, int seconds, ChildEnvironment environment = ChildEnvironment::Inherited,
                      const std::function<void(size_t)>& progress = {});
