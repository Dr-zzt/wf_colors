solutions = r"""U+0085 
U+00A0 
U+061C
U+115F
U+1160
U+1680 
U+180E 
U+2000 
U+2001 
U+2002 
U+2003 
U+2004 
U+2005 
U+2006 
U+2007 
U+2008 
U+2009 
U+200A 
U+200B 
U+200C 
U+200D 
U+200E
U+200F
U+2028 
U+2029 
U+202A
U+202B
U+202C
U+202D
U+202E
U+202F 
U+205F 
U+2060 
U+2066
U+2067
U+2068
U+2069
U+2427
U+2428
U+2429
U+242A
U+242B
U+242C
U+242D
U+242E
U+242F
U+2430
U+2431
U+2432
U+2433
U+2434
U+2435
U+2436
U+2437
U+2438
U+2439
U+243A
U+243B
U+243C
U+243D
U+243E
U+243F
U+2800
U+3000 
U+3164
U+FFA0
U+FEFF 
"""

if __name__ == '__main__':
    output = ""
    for line in solutions.splitlines():
        line = line.strip().strip("U+")
        if not line:
            continue
        output += '"\\u' + line + '", '
    print(output)