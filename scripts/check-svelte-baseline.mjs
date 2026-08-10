import { spawnSync } from 'node:child_process';
import path from 'node:path';

const limits = {
	errors: Number.parseInt(process.env.SVELTE_CHECK_MAX_ERRORS ?? '5432', 10),
	warnings: Number.parseInt(process.env.SVELTE_CHECK_MAX_WARNINGS ?? '124', 10),
	files: Number.parseInt(process.env.SVELTE_CHECK_MAX_FILES ?? '240', 10)
};

const executable = path.resolve('node_modules/svelte-check/bin/svelte-check');
const result = spawnSync(
	process.execPath,
	[executable, '--tsconfig', './tsconfig.json', '--output', 'machine'],
	{
		cwd: process.cwd(),
		encoding: 'utf8',
		maxBuffer: 64 * 1024 * 1024
	}
);

if (result.error) {
	throw result.error;
}

const output = `${result.stdout ?? ''}${result.stderr ?? ''}`;
const summaries = [
	...output.matchAll(
		/COMPLETED\s+\d+\s+FILES\s+(\d+)\s+ERRORS\s+(\d+)\s+WARNINGS\s+(\d+)\s+FILES_WITH_PROBLEMS/g
	)
];
const summary = summaries.at(-1);

if (!summary) {
	process.stderr.write(output);
	console.error('Unable to parse the svelte-check machine summary.');
	process.exit(result.status || 1);
}

const counts = {
	errors: Number.parseInt(summary[1], 10),
	warnings: Number.parseInt(summary[2], 10),
	files: Number.parseInt(summary[3], 10)
};

console.log(
	`Svelte baseline: ${counts.errors} errors, ${counts.warnings} warnings, ${counts.files} files ` +
		`(limits: ${limits.errors}/${limits.warnings}/${limits.files}).`
);

const exceeded = Object.entries(limits).filter(([key, limit]) => counts[key] > limit);
if (exceeded.length > 0) {
	for (const [key, limit] of exceeded) {
		console.error(`svelte-check ${key} increased to ${counts[key]} (limit ${limit}).`);
	}
	console.error('Run npm run check:raw for the complete diagnostics.');
	process.exit(1);
}

console.log('Svelte diagnostic baseline did not increase.');
