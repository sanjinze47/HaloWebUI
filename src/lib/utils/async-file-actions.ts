export const saveThenReindexFile = async <SaveResult, ReindexResult>({
	save,
	reindex
}: {
	save: () => Promise<SaveResult>;
	reindex: () => Promise<ReindexResult>;
}) => {
	const saveResult = await save();
	if (saveResult == null || saveResult === false) {
		throw new Error('File content was not saved.');
	}
	const reindexResult = await reindex();
	return { saveResult, reindexResult };
};

export type AttachmentRemoval<T> = {
	item: T;
	key: string | null;
};

export const getAttachmentKey = (item: {
	id?: string;
	itemId?: string;
	preview_url?: string;
}) => item.id ?? item.itemId ?? item.preview_url ?? null;

export const removeAttachment = async <
	T extends { id?: string; itemId?: string; preview_url?: string }
>({
	item,
	pending,
	deleteRemote,
	revokePreview
}: {
	item: T;
	pending: Set<string | T>;
	deleteRemote: (item: T) => Promise<void>;
	revokePreview: (previewUrl?: string) => void;
}): Promise<AttachmentRemoval<T> | null> => {
	const key = getAttachmentKey(item);
	const pendingKey = key ?? item;
	if (pending.has(pendingKey)) {
		return null;
	}

	pending.add(pendingKey);
	try {
		await deleteRemote(item);
		revokePreview(item.preview_url);
		return { item, key };
	} finally {
		pending.delete(pendingKey);
	}
};

export const removeDeletedAttachment = <
	T extends { id?: string; itemId?: string; preview_url?: string }
>(
	items: T[],
	removal: AttachmentRemoval<T>
) =>
	items.filter((candidate) =>
		removal.key ? getAttachmentKey(candidate) !== removal.key : candidate !== removal.item
	);
