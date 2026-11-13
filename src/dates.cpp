#include "dates.hpp"
#include <algorithm>
#include <cstdio>
#include <regex>
#include <stdexcept>

namespace {
int days_in_month(int year, int month) {
    const int days[]{31,28,31,30,31,30,31,31,30,31,30,31};
    return days[month-1] + (month == 2 && year % 4 == 0 && (year % 100 != 0 || year % 400 == 0));
}
}
bool valid_date(const std::string& date) {
    static const std::regex iso_date("[0-9]{4}-[0-9]{2}-[0-9]{2}");
    if (!std::regex_match(date, iso_date)) return false;
    int year = std::stoi(date.substr(0,4)), month = std::stoi(date.substr(5,2)), day = std::stoi(date.substr(8,2));
    return year >= 1900 && month >= 1 && month <= 12 && day >= 1 && day <= days_in_month(year, month);
}
std::string leading_date(const std::string& name) {
    if (name.size() < 10 || !valid_date(name.substr(0,10))) return "";
    if (name.size() > 10 && name[10] != ' ' && name[10] != '-' && name[10] != '_' && name[10] != '.') return "";
    return name.substr(0,10);
}
std::string six_month_cutoff(const std::string& today) {
    if (!valid_date(today)) throw std::runtime_error("Cannot calculate six-month cutoff from an invalid date.");
    int year = std::stoi(today.substr(0,4)), month = std::stoi(today.substr(5,2)) - 6;
    if (month < 1) { --year; month += 12; }
    int day = std::min(std::stoi(today.substr(8,2)), days_in_month(year, month));
    char date[40];
    std::snprintf(date, sizeof(date), "%04d-%02d-%02d", year, month, day);
    return date;
}
