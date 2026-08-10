import { describe, expect, it, vi } from 'vitest';

import {
	removeAttachment,
	removeDeletedAttachment,
	saveThenReindexFile
} from './async-file-actions';

describe('async file actions', () => {
	it('persists content before rebuilding the index', async () => {
		const calls: string[] = [];
		await saveThenReindexFile({
			save: async () => calls.push('save'),
			reindex: async () => calls.push('reindex')
		});

		expect(calls).toEqual(['save', 'reindex']);
	});

	it('does not rebuild the index when content persistence fails', async () => {
		const reindex = vi.fn();
		await expect(
			saveThenReindexFile({
				save: async () => {
					throw new Error('save failed');
				},
				reindex
			})
		).rejects.toThrow('save failed');
		expect(reindex).not.toHaveBeenCalled();
	});

	it('treats an empty persistence result as a failed save', async () => {
		const reindex = vi.fn();
		await expect(
			saveThenReindexFile({
				save: async () => null,
				reindex
			})
		).rejects.toThrow('File content was not saved.');
		expect(reindex).not.toHaveBeenCalled();
	});

	it('retains an attachment on deletion failure and deduplicates concurrent deletion', async () => {
		const items = [{ id: 'file-1', itemId: 'upload-1', preview_url: 'blob:test' }];
		const pending = new Set<string | (typeof items)[number]>();
		let rejectDelete: (error: Error) => void = () => {};
		const deleteRemote = vi.fn(
			() =>
				new Promise<void>((_resolve, reject) => {
					rejectDelete = reject;
				})
		);
		const revokePreview = vi.fn();

		const first = removeAttachment({ item: items[0], pending, deleteRemote, revokePreview });
		const duplicate = await removeAttachment({
			item: items[0],
			pending,
			deleteRemote,
			revokePreview
		});
		rejectDelete(new Error('delete failed'));

		await expect(first).rejects.toThrow('delete failed');
		expect(duplicate).toBeNull();
		expect(deleteRemote).toHaveBeenCalledTimes(1);
		expect(revokePreview).not.toHaveBeenCalled();
		expect(items).toHaveLength(1);
	});

	it('filters the latest attachment state when concurrent deletions finish out of order', async () => {
		type Attachment = { id: string };
		const first: Attachment = { id: 'file-1' };
		const second: Attachment = { id: 'file-2' };
		let files = [first, second];
		const pending = new Set<string | Attachment>();
		const resolvers = new Map<string, () => void>();
		const deleteRemote = (item: Attachment) =>
			new Promise<void>((resolve) => {
				resolvers.set(item.id, resolve);
			});

		const firstDeletion = removeAttachment({
			item: first,
			pending,
			deleteRemote,
			revokePreview: () => {}
		});
		const secondDeletion = removeAttachment({
			item: second,
			pending,
			deleteRemote,
			revokePreview: () => {}
		});

		resolvers.get('file-2')?.();
		const secondRemoval = await secondDeletion;
		if (secondRemoval) files = removeDeletedAttachment(files, secondRemoval);
		resolvers.get('file-1')?.();
		const firstRemoval = await firstDeletion;
		if (firstRemoval) files = removeDeletedAttachment(files, firstRemoval);

		expect(files).toEqual([]);
	});
});
