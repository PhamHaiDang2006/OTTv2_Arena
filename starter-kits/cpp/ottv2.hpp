#pragma once
#include <algorithm>
#include <array>
#include <cctype>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace ottv2 {
inline bool blue(char p) { return p >= 'A' && p <= 'Z'; }
inline std::string square(int i) { return std::string(1, char('a'+i%9)) + char('1'+i/9); }
inline int index(const std::string& s) {
    if(s.size()!=2 || s[0]<'a' || s[0]>'i' || s[1]<'1' || s[1]>'9') throw std::invalid_argument("square");
    return (s[1]-'1')*9+s[0]-'a';
}
struct Undo { int a,b; char piece,captured; };
struct Board {
    std::array<char,81> cells{};
    static Board parse(const std::string& fen) {
        Board b; std::istringstream input(fen); std::string rank; int y=8;
        while(std::getline(input,rank,'/')) {
            if(y<0) throw std::invalid_argument("ranks");
            int x=0;
            for(char c:rank) {
                if(c>='1' && c<='9') x+=c-'0';
                else if(std::string("BPKbpk").find(c)!=std::string::npos && x<9) b.cells[y*9+x++]=c;
                else throw std::invalid_argument("FEN token");
                if(x>9) throw std::invalid_argument("rank width");
            }
            if(x!=9) throw std::invalid_argument("rank width");
            --y;
        }
        if(y!=-1 || fen.empty() || fen.back()=='/') throw std::invalid_argument("ranks");
        return b;
    }
    std::string fen() const {
        std::string result;
        for(int y=8;y>=0;--y) {
            if(y!=8) result+='/'; int empty=0;
            for(int x=0;x<9;++x) {
                char p=cells[y*9+x];
                if(!p) ++empty;
                else { if(empty) result+=char('0'+empty); empty=0; result+=p; }
            }
            if(empty) result+=char('0'+empty);
        }
        return result;
    }
    std::vector<int> pieces(bool side, char kind=0) const {
        std::vector<int> out;
        for(int i=0;i<81;++i) if(cells[i] && blue(cells[i])==side && (!kind || std::toupper(cells[i])==kind)) out.push_back(i);
        return out;
    }
    std::vector<std::string> legal_moves(bool side) const {
        std::vector<std::string> out;
        for(int a:pieces(side)) for(int dy=-1;dy<=1;++dy) for(int dx=-1;dx<=1;++dx) {
            int x=a%9+dx,y=a/9+dy;
            if((!dx&&!dy)||x<0||x>=9||y<0||y>=9) continue;
            int b=y*9+x; if(b==(side?0:80)) continue;
            char p=std::toupper(cells[a]), q=cells[b], target=std::toupper(q);
            bool capture=(p=='B'&&target=='K')||(p=='K'&&target=='P')||(p=='P'&&target=='B');
            if(!q || (blue(q)!=side && capture)) out.push_back(square(a)+square(b));
        }
        std::sort(out.begin(),out.end()); return out;
    }
    Undo push(const std::string& move,bool side) {
        auto moves=legal_moves(side);
        if(!std::binary_search(moves.begin(),moves.end(),move)) throw std::invalid_argument("illegal move");
        int a=index(move.substr(0,2)), b=index(move.substr(2,2));
        Undo undo{a,b,cells[a],cells[b]}; cells[b]=cells[a]; cells[a]=0; return undo;
    }
    void pop(Undo u) { cells[u.a]=u.piece; cells[u.b]=u.captured; }
    Board apply(const std::string& move,bool side) const { Board b=*this; b.push(move,side); return b; }
};
inline void debug(const std::string& text) {
    std::istringstream in(text); std::string line;
    while(std::getline(in,line)) std::cout<<"# "<<line<<std::endl;
}
inline std::string choose(const Board& board,bool side,bool greedy,std::mt19937& rng) {
    auto moves=board.legal_moves(side);
    if(moves.empty()) throw std::runtime_error("no moves");
    if(!greedy) return moves[std::uniform_int_distribution<size_t>(0,moves.size()-1)(rng)];
    int goal=side?80:0;
    auto score=[&](const std::string& m) { int b=index(m.substr(2,2)); return std::make_tuple(b==goal,board.cells[b]!=0,-std::max(std::abs(b%9-goal%9),std::abs(b/9-goal/9))); };
    return *std::max_element(moves.begin(),moves.end(),[&](auto& a,auto& b){ return score(a)<score(b); });
}
template<class Select> void serve(Select select) {
    std::string line;
    if(!std::getline(std::cin,line)||line!="OTTV2 1") throw std::runtime_error("greeting");
    std::cout<<"READY CppStarter"<<std::endl;
    if(!std::getline(std::cin,line)||line.rfind("INIT ",0)!=0) throw std::runtime_error("INIT");
    bool side=line.find("side=BLUE")!=std::string::npos;
    std::cout<<"OK"<<std::endl;
    Board board; int remaining=0; bool state=false;
    while(std::getline(std::cin,line)) {
        if(line.rfind("STATE ",0)==0) {
            std::istringstream in(line); std::string cmd,fen,turn; int ply,opponent;
            if(!(in>>cmd>>fen>>turn>>ply>>remaining>>opponent)) throw std::runtime_error("STATE");
            if((turn=="BLUE")!=side) throw std::runtime_error("turn");
            board=Board::parse(fen); state=true;
        } else if(line=="GO" && state) {
            std::cout<<"MOVE "<<select(board,side,remaining)<<std::endl; state=false;
        } else if(line.rfind("END ",0)==0) return;
        else throw std::runtime_error("command");
    }
}
}
