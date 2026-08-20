import { EmptyState } from '../../components/ui';
import { Image } from 'lucide-react';

export function ImagesPage() {
  return (
    <div className="h-full flex items-center justify-center">
      <EmptyState
        icon={<Image className="w-16 h-16" />}
        title="Images"
        description="Screenshot gallery and image management"
      />
    </div>
  );
}
