export const CODE_BLOCK_COPY_TEXT_ATTRIBUTE = 'data-code-copy-text';
export const CODE_BLOCK_COPY_SELECTOR = `[${CODE_BLOCK_COPY_TEXT_ATTRIBUTE}]`;

export type CodeCopyPayload = {
	text: string;
	html: string;
};

export const preserveCodeBlockText = (textContent: string | null | undefined): string =>
	typeof textContent === 'string' ? textContent : '';

export const getCodeBlockElement = (node: Node | null): Element | null => {
	if (!node) {
		return null;
	}

	const element =
		node.nodeType === 1
			? (node as Element)
			: ((node as Node & { parentElement?: Element | null }).parentElement ?? null);

	return element?.closest(CODE_BLOCK_COPY_SELECTOR) ?? null;
};

export const getCodeBlockTextContent = (element: Element | null): string | null =>
	element?.getAttribute(CODE_BLOCK_COPY_TEXT_ATTRIBUTE) ?? null;

export const createCodeCopyPayload = (
	textContent: string | null | undefined,
	html: string
): CodeCopyPayload => ({
	text: preserveCodeBlockText(textContent),
	html
});
