#include "ottv2.hpp"

constexpr bool GREEDY = false; // true selects the greedy baseline.
std::mt19937 rng(1);

std::string choose_move(const ottv2::Board& board, bool blue, int remaining_ms) {
    return ottv2::choose(board, blue, GREEDY, rng);
}

int main() { ottv2::serve(choose_move); }
