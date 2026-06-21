# STM32H743VIT6 VS Code Environment

This workspace is prepared for STM32H743VIT6 development with ST-LINK.

## Installed tools

- VS Code
- CMake
- Ninja
- Arm GNU Toolchain: `arm-none-eabi-gcc`
- OpenOCD
- VS Code extensions:
  - C/C++
  - CMake Tools
  - Cortex-Debug
  - STM32 VS Code Extension

## Recommended project flow

1. Install STM32CubeMX and STM32CubeProgrammer from ST if they are not already installed.
2. In STM32CubeMX, create a new project for `STM32H743VIT6`.
3. In Project Manager, choose a CMake/STM32Cube or Makefile-compatible project format.
4. Generate the project into `D:\wenjian\dpj`, or into a subfolder under this directory.
5. Reopen this folder in VS Code.
6. Select the Arm GCC kit if CMake Tools asks.
7. Build with CMake Tools.

## ST-LINK debug note

For OpenOCD + Cortex-Debug, the usual target files are:

- Interface: `interface/stlink.cfg`
- Target: `target/stm32h7x.cfg`

After a CubeMX project is generated, create `.vscode/launch.json` in the generated project and point `executable` to the built `.elf` file.
