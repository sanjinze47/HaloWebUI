import { describe, expect, it } from 'vitest';

import { getCitationEntries } from './citations';

describe('citation source normalization', () => {
	it('keeps source order and metadata needed by citation markers', () => {
		const entries = getCitationEntries({
			source: {
				id: 'https://example.com/one',
				name: 'Example One',
				url: 'https://example.com/one'
			},
			document: ['First source'],
			metadata: [
				{
					source: 'web:https://example.com/one',
					name: 'Example One',
					url: 'https://example.com/one'
				}
			]
		});

		expect(entries).toHaveLength(1);
		expect(entries[0].document).toBe('First source');
		expect(entries[0].metadata.url).toBe('https://example.com/one');
	});

	it('falls back to metadata text when the document array is missing', () => {
		const entries = getCitationEntries({
			source: { id: 'https://example.com/two', name: 'Example Two' },
			metadata: [{ source: 'web:https://example.com/two', snippet: 'A short excerpt' }]
		});

		expect(entries[0].document).toBe('A short excerpt');
	});
});
