#include "ottv2.hpp"
int main() {
    std::string fen;
    while(std::getline(std::cin,fen)) {
        auto board=ottv2::Board::parse(fen);
        for(bool side:{true,false}) {
            for(auto& move:board.legal_moves(side)) {
                auto undo=board.push(move,side);
                board.pop(undo);
                if(board.fen()!=fen) return 2;
                std::cout<<move<<' ';
            }
            std::cout<<'\n';
        }
    }
}
