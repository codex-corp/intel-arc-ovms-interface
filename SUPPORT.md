# Support Guide

Thank you for using the **Intel Arc OVMS Interface**. We want to ensure you have the best experience running local AI on your Intel hardware.

## 🛠️ Self-Service Support

Before reaching out, please check these resources which cover 90% of common issues:

*   **[Installation Guide](./INSTALL.md)**: Step-by-step setup for Windows 11.
*   **[GPU Checklist](./gpu_checklist.md)**: Ensure ReBAR is enabled and drivers are up to date.
*   **[OOM Troubleshooting](./oom_troubleshooting.md)**: Fixes for "Out of Memory" errors on 8GB cards like the A750.
*   **[Connection Guide](./CONNECT_TOOLS.md)**: How to link this server to PhpStorm, VS Code, and other IDEs.

### 🔍 Quick Debugging
If the server isn't working as expected, run the health check script:
```powershell
.\verify_environment.ps1
```

---

## 🚀 Usage & Examples

### Starting the Server
The standard way to run the interface:
```powershell
.\run_server.ps1 -Proxy
```
*   `-Proxy`: Starts the IDE compatibility layer in the background.
*   `-VerboseOutput`: Shows detailed inference logs if you are debugging.

### Changing Models
You can switch to any of the Top 10 supported INT4 models:
```powershell
.\download_model.ps1 -Setup
```

### Using Open Interpreter
If you have [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter) installed, you can use it with the local server:
```powershell
.\run_interpreter.ps1
```
Or with a direct prompt:
```powershell
.\run_interpreter.ps1 "What is my GPU model?"
```

---

## 💬 Community & Issues

### GitHub Issues
If you've found a bug or have a feature request, please [open an issue](https://github.com/codex-corp/intel-arc-ovms-interface/issues).
*Please include the output of `.\verify_environment.ps1` in your report.*

### Feature Requests
We are currently looking for feedback on:
*   Support for additional Intel ARC GPUs (A580, A770).
*   Integration with more local-AI tools.
*   Performance benchmarks for specific IDE plugins.

---

## 📜 License
This project is licensed under the Apache License 2.0. Support is provided on a best-effort basis by the community.
