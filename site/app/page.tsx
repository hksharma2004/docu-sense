import { Ask, Footer, Nav } from "@/components/sections/chrome";
import {
  Agents, Benchmarks, CiteFeature, Hero, HowItWorks, Principles, ReadFeature, Stats, VersionsFeature,
} from "@/components/sections/content";

const Gap = () => <div className="gap" />;

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Gap />
        <Stats />
        <Gap />
        <ReadFeature />
        <Gap />
        <CiteFeature />
        <Gap />
        <VersionsFeature />
        <Gap />
        <HowItWorks />
        <Gap />
        <Benchmarks />
        <Gap />
        <Agents />
        <Gap />
        <Principles />
        <Gap />
        <Ask />
      </main>
      <Footer />
    </>
  );
}
