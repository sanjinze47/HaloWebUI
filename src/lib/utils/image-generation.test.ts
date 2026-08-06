import { describe, expect, it } from 'vitest';

import { parseNaturalImageSize } from './image-generation';

describe('parseNaturalImageSize', () => {
	it.each([
		['2048x1152', '2048x1152'],
		['2048\u00d71152', '2048x1152'],
		['\u5bbd 2048 \u9ad8 1152', '2048x1152'],
		['width: 2048, height: 1152', '2048x1152'],
		['16:9 2K', '2048x1152'],
		['\u6b63\u65b9\u5f62 2048', '2048x2048'],
		['square image 2048', '2048x2048']
	])('parses %s', (prompt, expected) => {
		expect(parseNaturalImageSize(prompt)).toBe(expected);
	});

	it('returns null when the requested dimensions are ambiguous', () => {
		expect(parseNaturalImageSize('make it larger')).toBeNull();
		expect(parseNaturalImageSize('16:9')).toBeNull();
	});
});
