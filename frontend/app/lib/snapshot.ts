/** `snapshot_id` ma postać `techqa@<rewizja>`; zwraca krótką rewizję (7 znaków). */
export function snapshotShort(snapshotId: string): string {
  const revision = snapshotId.includes("@")
    ? snapshotId.slice(snapshotId.indexOf("@") + 1)
    : snapshotId;
  return revision.slice(0, 7);
}

/** `chunk_set_id` ma postać `<snapshot_id>/<wariant>`; zwraca wariant zestawu. */
export function chunkSetVariant(chunkSetId: string): string {
  return chunkSetId.slice(chunkSetId.lastIndexOf("/") + 1);
}
