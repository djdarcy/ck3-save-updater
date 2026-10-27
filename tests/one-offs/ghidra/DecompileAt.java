// Decompile chosen functions of a binary imported WITHOUT auto-analysis (ck3.exe is 101 MB; a full analysis
// takes hours). Each argument is a function entry as an offset from the image base (from cdb's .fnent, which
// reads the PE unwind table). For each: disassemble, create the function, decompile, print the C, and list the
// strings and called functions it references.
//
// Run: analyzeHeadless <projdir> <proj> -import ck3.exe -noanalysis -scriptPath <this folder>
//        -postScript DecompileAt.java 0x23186e0 0x23189d0 ...  > out.txt
// @category ck3-save-migrator
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

public class DecompileAt extends GhidraScript {
    @Override
    public void run() throws Exception {
        Address base = currentProgram.getImageBase();
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        for (String arg : getScriptArgs()) {
            long off = Long.decode(arg);
            Address entry = base.add(off);
            new DisassembleCommand(entry, null, true).applyTo(currentProgram, monitor);
            Function f = getFunctionAt(entry);
            if (f == null) {
                new CreateFunctionCmd(entry).applyTo(currentProgram, monitor);
                f = getFunctionAt(entry);
            }
            println("==== ck3+" + arg + " (" + entry + ")" + (f == null ? " NO FUNCTION" : " " + f.getBody().getNumAddresses() + " bytes"));
            if (f == null) continue;
            // strings referenced by address constants in the body
            for (Instruction ins : currentProgram.getListing().getInstructions(f.getBody(), true)) {
                for (Reference r : ins.getReferencesFrom()) {
                    Address to = r.getToAddress();
                    if (r.getReferenceType().isCall()) {
                        println("  call " + ins.getAddress() + " -> ck3+0x" + Long.toHexString(to.subtract(base)));
                    } else if (currentProgram.getMemory().contains(to)) {
                        String s = readAscii(to);
                        if (s != null) println("  str  " + ins.getAddress() + " \"" + s + "\"");
                    }
                }
            }
            DecompileResults res = dec.decompileFunction(f, 120, monitor);
            if (res.decompileCompleted()) {
                println(res.getDecompiledFunction().getC());
            } else {
                println("  decompile failed: " + res.getErrorMessage());
            }
        }
    }

    private String readAscii(Address a) {
        try {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 120; i++) {
                byte b = currentProgram.getMemory().getByte(a.add(i));
                if (b == 0) break;
                if (b < 0x20 || b > 0x7e) return null;
                sb.append((char) b);
            }
            return sb.length() >= 4 ? sb.toString() : null;
        } catch (MemoryAccessException e) {
            return null;
        }
    }
}
