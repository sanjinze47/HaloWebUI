import { describe, expect, it } from 'vitest';

import {
	getCitationDomain,
	getCitationDisplayName,
	getCitationEntries,
	getCitationFaviconUrl,
	getCitationSourceUrl,
	hasUsefulCitationExcerpt,
	isPlaceholderCitationTitle,
	normalizeCitationUrl
} from './citations';

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

	it('normalizes direct and provider-prefixed citation URLs', () => {
		expect(normalizeCitationUrl('https://example.com/article')).toBe('https://example.com/article');
		expect(normalizeCitationUrl('web:https://example.com/article')).toBe(
			'https://example.com/article'
		);
		expect(normalizeCitationUrl('source (https://example.com/article).')).toBe(
			'https://example.com/article'
		);
	});

	it('prefers source metadata for external link and favicon details', () => {
		const citation = {
			id: 'web:https://fallback.example/article',
			metadata: { url: 'https://docs.example/reference' },
			source: { id: 'provider-source-1', name: 'Reference' }
		};

		expect(getCitationSourceUrl(citation)).toBe('https://docs.example/reference');
		expect(getCitationDomain(citation)).toBe('docs.example');
		expect(getCitationFaviconUrl(citation)).toContain('domain=docs.example');
	});

	it('does not turn file IDs or arbitrary text into external links', () => {
		expect(getCitationSourceUrl({ id: 'file-123', source: { name: 'Local file' } })).toBe('');
		expect(getCitationDomain('not a URL')).toBe('');
		expect(getCitationFaviconUrl({ id: 'file-123' })).toBe('');
	});

	it('replaces numeric upstream titles with the source domain', () => {
		const citation = {
			id: 'https://bbc.com/article',
			source: { name: '1', url: 'https://bbc.com/article' }
		};

		expect(isPlaceholderCitationTitle('1')).toBe(true);
		expect(getCitationDisplayName(citation)).toBe('bbc.com');
	});

	it('does not render a title-only citation as an excerpt', () => {
		expect(hasUsefulCitationExcerpt('1', 'bbc.com')).toBe(false);
		expect(hasUsefulCitationExcerpt('A real excerpt from the source.', 'bbc.com')).toBe(true);
	});
});
