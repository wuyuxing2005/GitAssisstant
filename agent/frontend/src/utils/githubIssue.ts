export function isGitHubIssueReference(value: string | undefined | null): boolean {
  const input = (value || "").trim();
  if (!input) {
    return false;
  }
  return /^#?\d+$/.test(input) || /github\.com\/[^/]+\/[^/]+\/issues\/\d+/i.test(input);
}
