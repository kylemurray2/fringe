###Final installation
install (PROGRAMS
        Stack.py
        DESTINATION ${FRINGE_PYDIR}
        COMPONENT pylib)

install (PROGRAMS
        Stack_fringe.py
        DESTINATION ${FRINGE_PYDIR}
        COMPONENT pylib)

install(PROGRAMS
    sequential_PL.py
    DESTINATION ${FRINGE_BINDIR}
    COMPONENT pyexec)

install(PROGRAMS
    sequential.py
    DESTINATION ${FRINGE_BINDIR}
    COMPONENT pyexec)
