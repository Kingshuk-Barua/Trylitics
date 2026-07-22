import { MapView } from '@/components/MapView';
import { Section } from '@/components/ui';

export const metadata = { title: 'Map · MAI' };

export default function MapPage() {
  return (
    <Section
      eyebrow="Deliverable 5 · visualisation"
      title="District choropleth"
      sub="Every one of 734 district polygons is coloured individually by its own index value — not one flat colour per state. Shading is by percentile within the distribution, because a bounded composite clustered in the middle would otherwise render the whole country in two indistinguishable shades. Click a state to zoom; click a district for its complete record."
    >
      <MapView />
    </Section>
  );
}
