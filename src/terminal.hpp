#pragma once
#include <string>
#include <string_view>

// Presentation only: never use the escaped result as a filesystem path.
std::string clean(std::string_view text);
