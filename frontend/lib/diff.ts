export interface DiffSeg {
  text: string;
  changed: boolean;
}

/** Word-level LCS diff for the side-by-side non-standard clause view.
 *  Returns per-side segments; `changed` marks words absent from the other side. */
export function diffWords(a: string, b: string): { left: DiffSeg[]; right: DiffSeg[] } {
  const A = a.split(/\s+/).filter(Boolean).slice(0, 500);
  const B = b.split(/\s+/).filter(Boolean).slice(0, 500);
  const m = A.length;
  const n = B.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let jj = n - 1; jj >= 0; jj--) {
      dp[i][jj] = A[i] === B[jj] ? dp[i + 1][jj + 1] + 1 : Math.max(dp[i + 1][jj], dp[i][jj + 1]);
    }
  }
  const left: DiffSeg[] = [];
  const right: DiffSeg[] = [];
  const push = (arr: DiffSeg[], text: string, changed: boolean) => {
    const last = arr[arr.length - 1];
    if (last && last.changed === changed) last.text += " " + text;
    else arr.push({ text, changed });
  };
  let i = 0;
  let jj = 0;
  while (i < m && jj < n) {
    if (A[i] === B[jj]) {
      push(left, A[i], false);
      push(right, B[jj], false);
      i++;
      jj++;
    } else if (dp[i + 1][jj] >= dp[i][jj + 1]) {
      push(left, A[i], true);
      i++;
    } else {
      push(right, B[jj], true);
      jj++;
    }
  }
  while (i < m) push(left, A[i++], true);
  while (jj < n) push(right, B[jj++], true);
  return { left, right };
}
