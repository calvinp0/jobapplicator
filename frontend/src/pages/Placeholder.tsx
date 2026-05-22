interface PlaceholderProps {
  routeName: string;
}

export function Placeholder({ routeName }: PlaceholderProps) {
  return (
    <section className="placeholder">
      <h2>{routeName}</h2>
      <p>This route is not yet implemented.</p>
    </section>
  );
}
