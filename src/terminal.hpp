#pragma once
#include <string>
#include <string_view>
#include <optional>

// Presentation only: never use the escaped result as a filesystem path.
std::string clean(std::string_view text);
// Immediate q/Q cancellation; other selections remain Enter-terminated.
std::optional<std::string> read_folder_selection();
