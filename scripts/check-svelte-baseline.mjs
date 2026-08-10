import { spawn } from 'node:child_process';
import path from 'node:path';

import { keepOutputTail, parseSvelteSummary } from './lib/svelte-baseline.mjs';

const limits = {
	errors: Number.parseInt(process.env.SVELTE_CHECK_MAX_ERRORS ?? '5432', 10),
	warnings: Number.parseInt(process.env.SVELTE_CHECK_MAX_WARNINGS ?? '124', 10),
	files: Number.parseInt(process.env.SVELTE_CHECK_MAX_FILES ?? '240', 10)
};

const executable = path.resolve('node_modules/svelte-check/bin/svelte-check');
const result = await new Promise((resolve, reject) => {
	const child = spawn(
		process.execPath,
		[executable, '--tsconfig', './tsconfig.json', '--output', 'machine'],
		{
			cwd: process.cwd(),
			stdio: ['ignore', 'pipe', 'pipe']
		}
	);
	let stdoutTail = '';
	let stderrTail = '';

	child.stdout.setEncoding('utf8');
	child.stderr.setEncoding('utf8');
	child.stdout.on('data', (chunk) => {
		stdoutTail = keepOutputTail(stdoutTail, chunk);
	});
	child.stderr.on('data', (chunk) => {
		stderrTail = keepOutputTail(stderrTail, chunk);
	});
	child.once('error', reject);
	child.once('close', (code, signal) => {
		resolve({ code, signal, stdoutTail, stderrTail });
	});
});

const summary = parseSvelteSummary(`${result.stdoutTail}\n${result.stderrTail}`);

if (!summary) {
	console.error(
		`Unable to parse the svelte-check machine summary (exit ${result.code ?? 'unknown'}, signal ${result.signal ?? 'none'}).`
	);
	const failureTail = `${result.stdoutTail}\n${result.stderrTail}`.slice(-8 * 1024);
	if (failureTail.trim()) {
		console.error('Last svelte-check output:');
		process.stderr.write(failureTail);
	}
	process.exitCode = result.code || 1;
} else {
	console.log(
		`Svelte baseline: ${summary.errors} errors, ${summary.warnings} warnings, ${summary.files} files ` +
			`(limits: ${limits.errors}/${limits.warnings}/${limits.files}).`
	);

	const exceeded = Object.entries(limits).filter(([key, limit]) => summary[key] > limit);
	if (exceeded.length > 0) {
		for (const [key, limit] of exceeded) {
			console.error(`svelte-check ${key} increased to ${summary[key]} (limit ${limit}).`);
		}
		console.error('Run npm run check:raw for the complete diagnostics.');
		process.exitCode = 1;
	} else {
		console.log('Svelte diagnostic baseline did not increase.');
	}
}
