import { afterEach, describe, expect, it, mock } from 'bun:test';
import { useMetadata } from '~/composables/useMetadata';
import type { Field } from '~/types/metadata';

const testGlobals = globalThis as any;

afterEach(() => {
  delete testGlobals.$fetch;
});

describe('useMetadata', () => {
  const sampleFields: Field[] = [{ key: 'title', label: 'Title', type: 'string' }];

  it('fetches and stores metadata schema', async () => {
    const fetchMock = mock(async () => ({ fields: sampleFields }));
    testGlobals.$fetch = fetchMock;
    const { metadataSchema, isLoading, fetchMetadata } = useMetadata();

    const fetchPromise = fetchMetadata();
    expect(isLoading.value).toBe(true);

    await fetchPromise;

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(isLoading.value).toBe(false);
    expect(metadataSchema.value).toEqual(sampleFields);
  });

  it('skips fetching when schema is already loaded unless forced', async () => {
    const fetchMock = mock(async () => ({ fields: sampleFields }));
    testGlobals.$fetch = fetchMock;
    const { fetchMetadata } = useMetadata();

    await fetchMetadata();
    await fetchMetadata();
    await fetchMetadata(true);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('handles fetch errors by clearing schema', async () => {
    const fetchMock = mock(async () => {
      throw new Error('network');
    });
    testGlobals.$fetch = fetchMock;
    const { metadataSchema, fetchMetadata } = useMetadata();

    await fetchMetadata();

    expect(metadataSchema.value).toEqual([]);
  });
});
