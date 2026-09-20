# Maned Language - Integration Contract

**Version:** 1.0.0
**Status:** Draft - Phase 0
**Last Updated:** 2026-05-27
**Compatibility:** Breaking changes allowed in 0.x.x and major versions only

---

## Version History

### Version 1.0.0 (2026-05-27) - Initial Draft
**Status:** Draft - Awaiting Design Review

**Changes:**
- Initial integration contract definition
- Lang → Board interface: IR format, memory layout, control registers
- Lang → OS interface: Runtime API, memory management, error handling
- Preliminary operation set: MATMUL, RELU, QUANTIZE, DEQUANTIZE, LOAD, STORE, TILE, SYNC, WAIT, SIGNAL
- Memory regions defined: Code (4MB), Data (508MB), Shared (256MB), FPGA regs (256MB)
- System call API defined: Task, memory, FPGA control, synchronization

**Breaking Changes:** N/A (initial version)

**Deprecations:** None

**Compatibility Notes:**
- This is a draft contract; all interfaces subject to change before Phase 1 freeze
- No implementation exists yet

---

## Semantic Versioning Scheme

This integration contract follows **Semantic Versioning 2.0.0**:

**Version Format:** `MAJOR.MINOR.PATCH`

**MAJOR version** (increments when incompatible API changes are made):
- Changes to IR instruction encoding format
- Changes to system call signatures or calling conventions
- Changes to memory layout that require recompilation
- Removal of operations or API functions
- Changes to register layout or MMIO addresses

**MINOR version** (increments when backward-compatible functionality is added):
- Addition of new IR operations
- Addition of new system calls
- Addition of new registers (without changing existing offsets)
- Addition of new error codes
- Extension of operation capabilities (e.g., new data types)

**PATCH version** (increments for backward-compatible bug fixes):
- Clarifications to documentation
- Bug fixes in specification text
- Minor wording improvements
- Corrections to examples

**Version Compatibility Rules:**
- **Major version 0.x.x:** Breaking changes allowed at any time (development phase)
- **Major version ≥1.x.x:** Breaking changes only on major version increments
- **Minor/Patch changes:** Must maintain backward compatibility
- **Deprecated features:** Marked for removal in next major version

**Version Freeze Points:**
- **Phase 1 completion:** Version 1.0.0 freeze (no breaking changes without major bump)
- **Phase 4 completion:** Version 2.0.0 freeze (production-ready single FPGA)
- **Phase 7 completion:** Version 3.0.0 freeze (production-ready multi-FPGA)

---

## Purpose

This document defines the interfaces between the Maned Language sub-project and its dependencies (maned_board and maned_os). These contracts ensure that all three sub-projects can develop in parallel with clear expectations about integration points.

---

## Interface: Lang → Board (Compiler to Hardware)

### Overview
The language compiler generates intermediate representation (IR) that the FPGA hardware executes. This interface defines the IR format, memory layout requirements, and control protocols.

### 1. Intermediate Representation Format

**IR Operations (Preliminary):**
```
# Matrix Operations
MATMUL <dest> <src1> <src2> <M> <N> <K>    # INT8 matrix multiply
RELU <dest> <src> <size>                    # ReLU activation
QUANTIZE <dest> <src> <scale> <zero>        # FP32 → INT8
DEQUANTIZE <dest> <src> <scale> <zero>      # INT8 → FP32

# Memory Operations
LOAD <dest> <addr> <size>                   # Load from memory
STORE <addr> <src> <size>                   # Store to memory
TILE <dest> <src> <tile_M> <tile_N>         # Partition matrix

# Control Flow
SYNC <barrier_id>                           # Synchronization barrier
WAIT <event_id>                             # Wait for completion
SIGNAL <event_id>                           # Signal completion
```

**IR Encoding:**
- Binary format: 64-bit instructions
- Opcode: 8 bits
- Operands: Up to 7 × 8-bit register/immediate fields
- Memory addresses: 32-bit physical addresses

> **Status note (2026-09-16).** The encoding above is the *preliminary FPGA*
> contract and has not been built. The IR that actually ships — to BARK x86
> workers and the Bark VM — is the versioned binary IR in
> `maned_lang/include/maned/ir/binary_ir.h`, and since gap_009 it has two
> versions:
>
> | | ABI v1 | ABI v2 |
> |---|---|---|
> | Instruction | 8 bytes | 16 bytes |
> | Value ids | u8 (256 slots) | u16 (4096 slots) |
> | Level field | u8 | u16 |
> | Nonzero CONST literal | refused | carried in `imm` |
>
> Version is negotiated per worker from the `ir` / `rf_slots` fields of
> `/api/status` (PROTOCOL_SPEC.md Section 6.1); absent = v1/256. When the FPGA
> interface is implemented it must be reconciled with that format, not with
> this sketch. See docs/language/03_IR_AND_PROTOCOLS.md.

**Contract:**
- Lang provides: IR generator from RPN AST
- Board provides: IR decoder and executor
- Evolution: IR will expand with new operations in Phase 3+

### 2. Memory Layout Requirements

**Memory Regions:**
```
0x0000_0000 - 0x003F_FFFF   Code segment (4MB)
0x0040_0000 - 0x1FFF_FFFF   Data segment (508MB)
0x2000_0000 - 0x2FFF_FFFF   Shared memory (256MB)
0x3000_0000 - 0x3FFF_FFFF   FPGA registers (256MB)
```

**Alignment Requirements:**
- Matrices: 128-byte alignment (for DMA burst efficiency)
- Scalars: 4-byte alignment
- Code: 64-byte alignment (cache line)

**Contract:**
- Lang provides: Memory layout generator respecting alignment
- Board provides: Memory controller with burst optimization
- OS provides: Memory allocator with alignment guarantees

### 3. Control Register Interface

**FPGA Control Registers (Memory-Mapped):**
```
Base Address: 0x3000_0000

Offset  | Register           | Access | Description
--------|-------------------|--------|----------------------------------
0x0000  | CONTROL           | R/W    | Start/stop/reset
0x0004  | STATUS            | R      | Idle/busy/error status
0x0008  | IR_ADDR           | R/W    | IR program start address
0x000C  | IR_SIZE           | R/W    | IR program size (bytes)
0x0010  | DATA_ADDR         | R/W    | Data segment start address
0x0014  | INTERRUPT_ENABLE  | R/W    | Interrupt enable mask
0x0018  | INTERRUPT_STATUS  | R      | Interrupt pending flags
0x001C  | ERROR_CODE        | R      | Error code (if STATUS = error)
```

**Control Flow:**
1. Lang writes IR_ADDR and IR_SIZE
2. Lang writes DATA_ADDR
3. Lang writes CONTROL = START
4. Board executes IR
5. Board sets STATUS = IDLE and triggers interrupt
6. Lang reads STATUS and ERROR_CODE

**Contract:**
- Lang provides: Register access wrappers in compiler runtime
- Board provides: Register implementation in FPGA
- OS provides: MMIO access and interrupt handling

### 4. Synchronization Primitives

**Barriers:**
- Up to 16 barrier IDs (0-15)
- All tasks must reach barrier before any proceed
- Hardware-assisted barrier implementation

**Events:**
- Up to 256 event IDs (0-255)
- One-to-many signaling (broadcast)
- Lock-free event queue

**Contract:**
- Lang provides: High-level sync primitives (barriers, events) in language
- Board provides: Hardware barrier counters and event queues
- OS provides: Event notification to user space

---

## Interface: Lang → OS (Language Runtime API)

### Overview
The language runtime makes OS calls to manage execution. This interface defines the system call API, memory management, and error handling.

### 1. Runtime System Calls

**Core API:**
```c
// Task Management
task_id_t maned_task_create(task_fn_t fn, void* arg, priority_t priority);
int maned_task_destroy(task_id_t task);
int maned_task_wait(task_id_t task);
int maned_task_yield(void);

// Memory Management
void* maned_alloc(size_t size, size_t alignment);
void maned_free(void* ptr);
void* maned_alloc_shared(size_t size, numa_node_t node);
int maned_prefetch(void* addr, size_t size);

// FPGA Control
fpga_handle_t maned_fpga_acquire(fpga_id_t fpga);
int maned_fpga_release(fpga_handle_t handle);
int maned_fpga_execute(fpga_handle_t handle, ir_program_t* program);
int maned_fpga_wait(fpga_handle_t handle);

// Synchronization
barrier_t maned_barrier_create(int count);
int maned_barrier_wait(barrier_t barrier);
event_t maned_event_create(void);
int maned_event_wait(event_t event);
int maned_event_signal(event_t event);

// Error Handling
error_t maned_get_last_error(void);
const char* maned_error_string(error_t error);
```

**Calling Convention:**
- x86-64 System V ABI (for simulation)
- RISC-V ABI (for embedded target)
- Return codes: 0 = success, negative = error code

**Contract:**
- Lang provides: Runtime library wrapping OS calls
- OS provides: System call implementation (<1 µs latency)
- Evolution: API will expand with new features in Phase 3+

### 2. Memory Management

**Allocation Strategies:**
- **maned_alloc:** General-purpose allocation from unified memory
- **maned_alloc_shared:** NUMA-aware allocation for multi-FPGA
- **maned_prefetch:** DMA prefetch for future access

**Zero-Copy Requirements:**
- All allocations are DMA-capable
- No hidden copies in OS
- Memory is physically contiguous for DMA

**Contract:**
- Lang provides: Memory lifetime management in compiler
- OS provides: Fast allocator (<1 µs), zero-copy guarantees, DMA-capable buffers

### 3. Error Handling Protocol

**Error Codes (Preliminary):**
```
MANED_OK = 0
MANED_ERR_INVALID_ARG = -1
MANED_ERR_OUT_OF_MEMORY = -2
MANED_ERR_TIMEOUT = -3
MANED_ERR_FPGA_ERROR = -4
MANED_ERR_TASK_FAILED = -5
MANED_ERR_NOT_READY = -6
MANED_ERR_PERMISSION = -7
```

**Error Propagation:**
1. OS sets error code in thread-local storage
2. Lang runtime checks return codes
3. Lang propagates errors to user code (exceptions or Result types)

**Contract:**
- Lang provides: Error handling in user-facing API
- OS provides: Error codes, thread-local error storage
- Board provides: Hardware error reporting via registers

### 4. Performance Monitoring Hooks

**Counters (Preliminary):**
- Task execution time
- Memory allocation time
- FPGA execution time
- IPC latency
- DMA bandwidth

**API:**
```c
int maned_perf_start(perf_counter_t counter);
int maned_perf_stop(perf_counter_t counter);
uint64_t maned_perf_read(perf_counter_t counter);
```

**Contract:**
- Lang provides: High-level profiling API in language
- OS provides: Low-overhead counter implementation (<10ns)
- Board provides: Hardware performance counters

---

## Interface Evolution and Versioning

### Version 1.0 (Phase 0-1)
- Draft interfaces defined
- No implementation yet
- Focus: Planning and architecture

### Version 1.1 (Phase 2-3)
- Basic implementations
- Single FPGA support
- Core operations only (matmul, relu)

### Version 2.0 (Phase 4-5)
- Multi-FPGA support
- Extended operation set
- Optimized performance

### Version 3.0 (Phase 6+)
- Production features
- Advanced optimizations
- Full operation coverage

---

## Design Review Checkpoints

At each sprint boundary, integration contracts are reviewed:

1. **Do interfaces still match assumptions?**
   - Verify register layout is sufficient
   - Verify system call latency is achievable
   - Verify memory model is compatible

2. **Are there new dependencies?**
   - New operations requiring new hardware
   - New OS features required
   - New synchronization primitives

3. **Performance validation:**
   - Benchmark system call overhead
   - Measure FPGA control latency
   - Profile memory allocation

---

## Open Questions (To Be Resolved)

### Phase 0 Questions
1. **IR Format:** Binary vs. text? Fixed 64-bit vs. variable length?
2. **Memory Model:** Virtual memory or physical only?
3. **Error Handling:** Exceptions vs. error codes in language?
4. **Threading Model:** OS threads or language-level green threads?

### Phase 1 Questions
1. **Multi-FPGA:** How to partition workloads across FPGAs?
2. **Scheduling:** OS-level scheduling or language-level?
3. **Optimization:** Where does optimization happen (compiler vs. OS)?

These questions will be resolved through PDCA cycles at sprint boundaries.

---

## Contract Validation

### Phase 2 (Proof of Concept)
- Implement minimal IR (matmul only)
- Implement core system calls (task, memory, fpga)
- End-to-end test: compile → run → verify

### Phase 3 (Core Building Blocks)
- Extend IR with 10+ operations
- Implement all memory management calls
- Performance validation: <1 µs system call latency

### Phase 4 (Single FPGA Integration)
- Complete IR implementation
- Complete system call API
- Full integration test suite

---

## Dependencies

**maned_lang depends on:**
- maned_board: IR execution, register interface, hardware synchronization
- maned_os: Runtime API, memory management, task management

**Contract guarantees needed from dependencies:**
- Board: IR execution correctness, <100ns interrupt latency
- OS: <1 µs system call latency, zero-copy memory, DMA-capable allocations

---

## Success Criteria

This integration contract is successful if:

- ✅ All three sub-projects can develop in parallel
- ✅ Interface mismatches are caught early (design review)
- ✅ Integration happens incrementally (Phase 2 → Phase 4)
- ✅ Performance targets are met (<1 µs syscalls, 75-85% memory BW)
- ✅ Changes to interfaces are documented and versioned

---

**Status:** 📄 Draft - Awaiting Design Review
**Next Review:** Sprint 1 Approval (Phase 1 completion)
**Owned By:** Language Designer + System Architect

---

_"Clear interfaces enable parallel development and reduce integration risk."_
