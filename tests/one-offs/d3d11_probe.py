"""Can this machine create a hardware Direct3D 11 device right now?

CK3 dies at startup with "Failed creating DX11 device / Not enough memory resources"
(gfx_dx11_master_context.cpp:261) when the answer is no. This asks the same question
without the game: D3D11CreateDevice on the default hardware adapter, then on WARP
(software) as a control. hr 0x8007000E = E_OUTOFMEMORY from the driver stack; a
graphics-driver restart (Win+Ctrl+Shift+B) or a reboot is the fix, not anything in CK3.

Usage: python -I d3d11_probe.py      (exit 0 if hardware works, 2 if only WARP works, 3 if neither)
"""
import ctypes
import sys

D3D_DRIVER_TYPE_HARDWARE = 1
D3D_DRIVER_TYPE_WARP = 5
D3D11_SDK_VERSION = 7


def create(driver_type: int) -> tuple[int, int]:
    d3d11 = ctypes.windll.d3d11
    dev = ctypes.c_void_p()
    ctx = ctypes.c_void_p()
    level = ctypes.c_uint()
    hr = d3d11.D3D11CreateDevice(None, driver_type, None, 0, None, 0, D3D11_SDK_VERSION,
                                 ctypes.byref(dev), ctypes.byref(level), ctypes.byref(ctx))
    return hr & 0xFFFFFFFF, level.value


def main() -> int:
    hw, hw_level = create(D3D_DRIVER_TYPE_HARDWARE)
    warp, warp_level = create(D3D_DRIVER_TYPE_WARP)
    print(f"hardware: hr=0x{hw:08x} feature_level=0x{hw_level:x}")
    print(f"warp    : hr=0x{warp:08x} feature_level=0x{warp_level:x}")
    if hw == 0:
        print("OK: hardware DX11 device creation works; CK3 should start.")
        return 0
    if warp == 0:
        print("BAD: only the software (WARP) device works -> GPU driver stack is wedged. "
              "Restart the graphics driver (Win+Ctrl+Shift+B) or reboot, then re-run.")
        return 2
    print("BAD: neither works -> D3D runtime problem, not just the driver.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
