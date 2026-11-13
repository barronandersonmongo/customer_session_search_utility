#include "dates.hpp"
#include <iostream>
#include <stdexcept>
int main() {
    try {
        for (const auto& example : {std::pair{"2026-11-13", "2026-05-13"}, {"2025-03-15", "2024-09-15"},
                                    {"2024-08-31", "2024-02-29"}, {"2025-08-31", "2025-02-28"},
                                    {"2025-01-31", "2024-07-31"}})
            if (six_month_cutoff(example.first) != example.second) throw std::runtime_error("Calendar-month cutoff mismatch.");
        if (!valid_date("2024-02-29") || valid_date("2025-02-29")) throw std::runtime_error("Leap-year mismatch.");
        if (leading_date("2026-11-01 - Notes.txt") != "2026-11-01" || !leading_date("2026-11-01x").empty())
            throw std::runtime_error("Date-prefix mismatch.");
        std::cout << "Calendar cutoffs and metadata dates passed.\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
