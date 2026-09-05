<img width="975" height="969" alt="Jane_Street_Puzzle_Solution" src="https://github.com/user-attachments/assets/26161227-207e-4e64-9f92-12f47d39c872" />

# Reverse-Engineering-An-ASIC-Jane-Street-Puzzle-8-5-2026-
Here is my submission of the Jane Street Puzzle: ["Can you reverse engineer an ASIC"](https://blog.janestreet.com/can-you-reverse-engineer-an-asic/). Here I cover some of my process for figuring out the solutions and what tools I used. 

# GDS to SPICE
The first tool I used to convert GDS to SPICE is the open-source EDA tool [MagicVLSI](https://opencircuitdesign.com/magic/). I ran everything through WSL (Windows Subsystem for Linux). After checking the different parts on the TinyTapeout Online GDS Viewer linked in the GitHub repo for the puzzle, we are able to tell the PDK used is the open-source SKY130 PDK. Thus, I used a .magicrc file to load up magic with the SKY130 PDK (which is a technology file for the case of magic). To utilize/install the PDK, there are various methods, but I used [OpenPDK](https://opencircuitdesign.com/open_pdks/). 
```
magic
```
This starts MagicVLSI, then, in the console:
```
%gds read puzzle.gds
%load puzzle
%extract do local
%extract all
%ext2spice lvs
%ext2spice -o puzzle.spice
```
This process might take a second, but after running everything, you should get a file in your local directory named "puzzle.spice". Also note that while running this, there should have been two errors: 
```
Reading "INTERNAL_7".
Error while reading cell "INTERNAL_7" (byte position 120): Unknown layer/datatype in boundary, layer=200 type=0
Reading "INTERNAL_3".
Error while reading cell "INTERNAL_3" (byte position 230): Unknown layer/datatype in boundary, layer=200 type=0
```
This is still correct, and more on that later. 

# SPICE to Verilog
Looking at puzzle.spice, we can see that the hierarchy is actually well kept by magic, resulting in an already structural gate-level netlist, and the translation is mostly mechanical. Here I just told Claude to generate the Python code for conversion linked in "spice2v.py"

# How to Turn on the "Success?"
I was actually stuck at this stage for a while. There was only one input, and from the Verilog netlist, you can see a lot of different flip-flops; thus, the obvious assumption is that we need to send in a sequence of inputs after the rst_n over different clock cycles to turn on "success". The problem is, how do we figure that out, and how many clock cycles should we use?

This got me stuck for a long time before I took a look back at the [example_inputs.vcd](https://github.com/janestreet/asic-puzzle-2026/blob/master/example_inputs.vcd) Jane Street provided, which contains an output after 121 inputs since "enable" was held high. Also, in both attempts, the outputs return bits that, when decoded with ASCII, say "TRY AGAIN". This gives the main idea for solving the puzzle: we can take a more brute-force approach to solve for "success" by inputting different values for the 121 bits. 

The brute-force approach is basically to describe the circuit as a boolean formula and hand it to a SAT solver (I used Z3 in this case, which is actually a much more powerful SMT solver that also has a Python API to allow building Boolean expressions (and, or, not, xor, if) as ordinary Python objects). This script lives in "solve_netlist.py" and was also written by Claude; it made a few mistakes when converting Verilog, but after a few rounds of bug fixing, everything worked out! 

I verified everything works in a testbench "tb_puzzle.v" which was run in WSL as well through iVerilog. Giving me the solution, which is at the bottom of this README.

# Another Way (A Better Way):
However, this brute-force way of solving the puzzle felt kind of wrong, so I did a bit more research on another result I accidentally got in the middle of testing: "TWO NOT TOUCH". This is an alternate name of the "Star Battle" puzzles, where there are different regions in an N x N square grid. To solve this puzzle, we have to fill the grid with stars such that each row, column, and region contains exactly two stars, with no stars touching each other. With 121 bits, this could be an 11x11 Star Battle puzzle. With this hypothesis, I went back to count the number of 1's in the solution, giving me exactly 22. Loving a new puzzle, I went down the path to find out how to solve this ASIC in a better way by recreating the Star Battle/Two Not Touch puzzle and solving that. 

# Recreating the Puzzle:
The problem we now face is recreating the puzzle. Because the puzzle has to track two stars per region and two stars per row/column, if we just input 1 at position p (p from 0 to 120) and 0 everywhere else, looking at the flops, we should be able to tell which corresponds to different regions. Then, looking at the flops that create exact partitions of all positions, we can find the ones that are useful for reconstruction. Going off this idea, I asked Claude to create a script and it found 3 sets fitting this condition: 
```
Set 0:  1 group,  sizes=[121]                                  -> globa count
Set 1: 11 groups, sizes=[4,5,6,7,8,8,9,11,14,21,28]            -> regions
Set 2: 11 groups, sizes=[11,11,11,11,11,11,11,11,11,11,11]     -> cols
```
Running probe_regions.py gives:
```
region map:
   A A A A A B B C D D E
   A A F A A B C C D D E
   A A F B B B B C C D E
   A A F B G G G E C C E
   F A F B G E E E E E E
   F F F B G G G E H H H
   B B B B B B G E H I I
   B J J J G G G E H I I
   B J J K E E E E H I I
   B B J K K E E E H H H
   B J J K E E E E E E E
```
Solving this puzzle by the rules, we get the same solution as the brute force method (puzzle solution shown at the top of the README). 


## The Solution:
```
(* TWO STARS *)
```

Produced by this 121-bit input, fed MSB-first over 121 cycles while `enable` is high:

```
0000000101010000100000000000010101010000000000001010000001000001000000100000101000010000000100000010000010010001010000000
```

# Easter Eggs:
Egg 0: JSC in the puzzle as seen at the top of the README

Egg 1: "EMPTY SKY" 
ASCII output when setting all 121 bits to 0.

Egg 2: "BIG BANG" 
ASCII output when setting all 121 bits to 1.

Egg 3: "The night sky awaits"
Using the lower 7 bits of 11 bits word of the inputs in "example_inputs.vcd" we get the ASCII outputs:
"The night s"
"ky awaits"

Egg 4: More on example_inputs.vcd:
The version was not a version: 
```
$version
    Leave no stone unturned! But for this file, consider looking at it in a waveform viewer instead.
$end
```
The date was the most recent leap second added to Coordinated Universal Time (UTC) 
```
$date
  Sat Dec 31 23:59:60 2016
$end
```

Egg 5: "PER ARENAM AD ASTRA"
I actually did not get this one; remember the INTERNAL 3 and 7 at the start when we loaded the GDS file into Magic? I never knew what they did and did not figure it out, so I asked Claude specifically about these two components, and it gave the result below:
```
# ### ### #   #   # ### #       # ###   # ### #   #   ### #   # ###   ### ###       # ###   ### # #       # ###   # # #   ###   # ### #   # ###
.--.  .  .-.     .-  .-.  .  -.  .-  --     .-  -..     .-  ...  -  .-.  .-
```
which translates through Morse Code to PER ARENAM AD ASTRA --- Claude's explanation --> "'Through the sand, to the stars' — arena being Latin for sand, i.e. silicon. A pun on per aspera ad astra, and a direct nod to what the puzzle turns out to be about."
