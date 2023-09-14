cd ../../build
CXX=${CXX} cmake -DCMAKE_INSTALL_PREFIX=../install ../src/fringe
make all
make install
