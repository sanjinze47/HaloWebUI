import { describe, expect, it } from 'vitest';

import {
	CODE_BLOCK_COPY_TEXT_ATTRIBUTE,
	createCodeCopyPayload,
	preserveCodeBlockText
} from './code-copy';

describe('code block copy', () => {
	it('preserves multi-level Python indentation', () => {
		const code = 'def outer():\n    if ready:\n        for item in items:\n            print(item)\n    return None';

		expect(preserveCodeBlockText(code)).toBe(code);
	});

	it('preserves spaces in JSON, YAML, and shell code', () => {
		const samples = [
			'{\n  "nested": {\n    "value": true\n  }\n}',
			'service:\n  command: "echo  two spaces"\n  environment:\n    KEY: value',
			'if [ "$1" = "x" ]; then\n  printf "  %s\\n" "$1"\nfi'
		];

		for (const code of samples) {
			expect(preserveCodeBlockText(code)).toBe(code);
		}
	});

	it('preserves leading whitespace, blank lines, and a trailing newline', () => {
		const code = '\n  first line\n\n    nested line\n';

		expect(preserveCodeBlockText(code)).toBe(code);
	});

	it('keeps HTML and plain-text clipboard formats together', () => {
		const text = '  const value = 1;\n';
		const html = '<pre><code><span class="hljs-keyword">const</span> value = 1;</code></pre>';

		expect(createCodeCopyPayload(text, html)).toEqual({ text, html });
		expect(CODE_BLOCK_COPY_TEXT_ATTRIBUTE).toBe('data-code-copy-text');
	});
});
