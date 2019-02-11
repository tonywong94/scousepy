# Licensed under an MIT open source license - see LICENSE

"""

SCOUSE - Semi-automated multi-COmponent Universal Spectral-line fitting Engine
Copyright (c) 2016-2018 Jonathan D. Henshaw
CONTACT: henshaw@mpia.de

"""

class colors:
    _reset_='\033[0m'
    _bold_='\033[01m'
    _disable_='\033[02m'
    _underline_='\033[04m'
    _reverse_='\033[07m'
    _strikethrough_='\033[09m'
    _invisible_='\033[08m'
    _endc_ = '\033[0m'

    class fg:
        _black='\033[30m'
        _red_='\033[31m'
        _green_='\033[32m'
        _orange_='\033[33m'
        _blue_='\033[34m'
        _purple_='\033[35m'
        _cyan_='\033[36m'
        _lightgrey_='\033[37m'
        _darkgrey_='\033[90m'
        _lightred_='\033[91m'
        _lightgreen_='\033[92m'
        _yellow_='\033[93m'
        _lightblue_='\033[94m'
        _pink_='\033[95m'
        _lightcyan_='\033[96m'
    class bg:
        _black_='\033[40m'
        _red_='\033[41m'
        _green_='\033[42m'
        _orange_='\033[43m'
        _blue_='\033[44m'
        _purple_='\033[45m'
        _cyan_='\033[46m'
        _lightgrey_='\033[47m'
