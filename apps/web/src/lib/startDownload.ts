// Opens a download link. The store sends the file with `Content-Disposition: attachment` (NAMING §9), so the
// browser saves it and the page stays where it is. Its own module, so tests can replace it.
export function startDownload(url: string): void {
  window.location.assign(url);
}
