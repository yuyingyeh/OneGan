import torch
import torch.nn as nn
from PIL import Image
import torchvision.transforms as F

import onegan as ohgan
from onegan.data.loader import collect_images, load_image


class InpaintDastaset(ohgan.data.BaseDastaset):

    def __init__(self, roots, target_size, **kwargs):
        self.roots = roots
        self.target_size = target_size
        self.sources = collect_images(roots[0])
        self.targets = collect_images(roots[1])
        self.transform = F.Compose([
            F.Resize(target_size, interpolation=Image.BICUBIC),
            F.ToTensor(),
            F.Normalize(mean=[.5, .5, .5], std=[.5, .5, .5])
        ])
        self.debug = kwargs.get('debug')

    def __getitem__(self, index):
        masked = load_image(self.sources[index]).convert('RGB')
        image = load_image(self.targets[index]).convert('RGB')
        return self.transform(masked), self.transform(image)

    def __len__(self):
        return len(self.sources)


if __name__ == '__main__':
    conditional = True

    roots = [
        '../human-recovery/datasets/bmvc/bmvc_flowers/train_128/inputs/scribble',
        '../human-recovery/datasets/bmvc/bmvc_flowers/train_128/gt/'
    ]
    loader_args = dict(batch_size=32, num_workers=4, pin_memory=True)
    dataset = InpaintDastaset(roots, target_size=(128, 128), debug=False)
    train_loader = ohgan.data.create_dataloader(dataset, phase='train', **loader_args)
    val_loader = ohgan.data.create_dataloader(dataset, phase='val', **loader_args)

    def make_optimizer(model):
        return torch.optim.Adam(model.parameters(), lr=0.0001, betas=(0.5, 0.999))

    g = ohgan.external.pix2pix.define_G(3, 3, 64, 'unet_128', init_type='xavier').cuda()
    d = ohgan.external.pix2pix.define_D(6 if conditional else 3, 64, 'basic', init_type='xavier').cuda()

    gan_criterion = (ohgan.losses.GANLoss(conditional)
                     .add_term('smooth', nn.L1Loss(), weight=100)
                     .add_term('adv', ohgan.losses.AdversarialLoss(d), weight=1)
                     .add_term('gp', ohgan.losses.GradientPaneltyLoss(d), weight=0.25))
    metric = ohgan.metrics.Psnr()

    estimator = ohgan.estimator.OneGANEstimator(
        model=(g, d),
        optimizer=(make_optimizer(g), make_optimizer(d)),
        criterion=gan_criterion,
        metric=metric,
        saver=ohgan.utils.GANCheckpoint(save_epochs=5),
        name='flowers'
    )
    estimator.run(train_loader, val_loader, epochs=50)
