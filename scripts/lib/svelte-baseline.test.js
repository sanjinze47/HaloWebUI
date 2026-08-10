import { describe, expect, it } from 'vitest';

import { keepOutputTail, parseSvelteSummary } from './svelte-baseline.mjs';

describe('Svelte diagnostic baseline parser', () => {
	it('parses the final machine summary across platforms', () => {
		const output = [
			'123 START "/workspace"',
			'124 COMPLETED 100 FILES 10 ERRORS 2 WARNINGS 4 FILES_WITH_PROBLEMS\r',
			'125 COMPLETED 200 FILES 9 ERRORS 1 WARNINGS 3 FILES_WITH_PROBLEMS'
		].join('\n');

		expect(parseSvelteSummary(output)).toEqual({ errors: 9, warnings: 1, files: 3 });
	});

	it('returns null when a terminated check has no completion record', () => {
		expect(parseSvelteSummary('123 FAILURE "worker stopped"')).toBeNull();
	});

	it('retains only the bounded output tail', () => {
		expect(keepOutputTail('abcdef', 'ghij', 6)).toBe('efghij');
	});
});
