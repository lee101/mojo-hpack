	.att_syntax
	.file	"probe3.mojo"
	.text
	.prefalign	4, .Lfunc_end0, nop
	.type	main_closure_0,@function
main_closure_0:
	.cfi_startproc
	jmp	KGEN_CompilerRT_AsyncRT_GetOrCreateCPUDevice@PLT
.Lfunc_end0:
	.size	main_closure_0, .Lfunc_end0-main_closure_0
	.cfi_endproc

	.prefalign	4, .Lfunc_end1, nop
	.type	main_closure_1,@function
main_closure_1:
	.cfi_startproc
	jmp	KGEN_CompilerRT_AsyncRT_ReleaseCPUDevice@PLT
.Lfunc_end1:
	.size	main_closure_1, .Lfunc_end1-main_closure_1
	.cfi_endproc

	.globl	main
	.prefalign	4, .Lfunc_end2, nop
	.type	main,@function
main:
.Lmain$local:
	.type	.Lmain$local,@function
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	pushq	%rbx
	.cfi_def_cfa_offset 24
	pushq	%rax
	.cfi_def_cfa_offset 32
	.cfi_offset %rbx, -24
	.cfi_offset %rbp, -16
	movq	%rsi, %rbx
	movl	%edi, %ebp
	callq	KGEN_CompilerRT_AsyncRT_GetCurrentCPUDevice@PLT
	testq	%rax, %rax
	je	.LBB2_1
	movl	%ebp, %edi
	movq	%rbx, %rsi
	callq	KGEN_CompilerRT_SetArgV@PLT
	callq	KGEN_CompilerRT_PrintStackTraceOnFault@PLT
.LBB2_1:
	leaq	static_string_a61c3395ab9379d9(%rip), %rdi
	movq	main_closure_0@GOTPCREL(%rip), %rdx
	movq	main_closure_1@GOTPCREL(%rip), %rcx
	movl	$7, %esi
	callq	KGEN_CompilerRT_GetOrCreateGlobal@PLT
	movl	%ebp, %edi
	movq	%rbx, %rsi
	callq	KGEN_CompilerRT_SetArgV@PLT
	callq	KGEN_CompilerRT_PrintStackTraceOnFault@PLT
.Lfunc_end2:
	.size	main, .Lfunc_end2-main
	.size	.Lmain$local, .Lfunc_end2-main
	.cfi_endproc

	.section	.rodata.cst8,"aM",@progbits,8
	.p2align	3, 0x0
	.type	.LCPI31_0,@object
.LCPI31_0:
	.quad	64
	.size	.LCPI31_0, 8
	.text
	.globl	p3_shift
	.prefalign	4, .Lfunc_end3, nop
	.type	p3_shift,@function
p3_shift:
.Lp3_shift$local:
	.type	.Lp3_shift$local,@function
	vmovdqu	(%rdi), %ymm0
	vmovdqu	32(%rdi), %ymm1
	vpsllvq	%ymm1, %ymm0, %ymm2
	vpbroadcastq	.LCPI31_0(%rip), %ymm3
	vpsubq	%ymm1, %ymm3, %ymm1
	vpsrlvq	%ymm1, %ymm0, %ymm0
	vpor	%ymm2, %ymm0, %ymm0
	vpshufd	$238, %xmm0, %xmm1
	vpermq	$255, %ymm0, %ymm0
	vpaddq	%xmm0, %xmm1, %xmm0
	vmovq	%xmm0, %rax
	incq	%rax
	vzeroupper
	retq
.Lfunc_end3:
	.size	p3_shift, .Lfunc_end3-p3_shift
	.size	.Lp3_shift$local, .Lfunc_end3-p3_shift

	.type	static_string_a61c3395ab9379d9,@object
	.section	.rodata,"a",@progbits
	.p2align	4, 0x0
static_string_a61c3395ab9379d9:
	.asciz	"Runtime"
	.size	static_string_a61c3395ab9379d9, 8

	.section	".note.GNU-stack","",@progbits
