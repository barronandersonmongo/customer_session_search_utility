#pragma once
#include <string>
#include <string_view>
#include <optional>

// Presentation only: never use the escaped result as a filesystem path.
std::string clean(std::string_view text);
// Read one immediate selection key; q/Q cancels and Enter selects the default.
std::optional<std::string> read_folder_selection();

inline constexpr std::string_view folder_selection_keys = "abcdefghijklmnoprstuvwxyz";
