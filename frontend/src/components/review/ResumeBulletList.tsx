interface ResumeBulletListProps {
  bullets: string[];
}

/** Document-style bullet list with hanging indent and aligned markers. */
export function ResumeBulletList({ bullets }: ResumeBulletListProps) {
  if (bullets.length === 0) return null;
  return (
    <ul className="doc-bullets">
      {bullets.map((bullet, idx) => (
        <li key={idx}>{bullet}</li>
      ))}
    </ul>
  );
}
