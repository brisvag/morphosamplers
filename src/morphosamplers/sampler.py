"""Tools for image resampling."""

from typing import Tuple, Union

import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial.transform import Rotation

from .spline import Spline3D
from .surface_spline import SplineSurfaceGrid


def generate_3D_grid(
    grid_shape: Tuple[int, int, int] = (10, 10, 10),
    grid_spacing: Tuple[float, float, float] = (1, 1, 1),
    squeeze: bool = True,
) -> np.ndarray:
    """
    Generate a 3D sampling grid with specified shape and spacing.

    The grid generated is centered on the origin, has shape (m, n, p, 3) for
    grid_shape (m, n, p), and spacing grid_spacing between neighboring points.

    Parameters
    ----------
    grid_shape : Tuple[int, int, int]
        The number of grid points along each axis.
    grid_spacing : Tuple[float, float, float]
        Spacing between points in the sampling grid.
    squeeze: bool
        Discard degenerate dimensions in the output.

    Returns
    -------
    np.ndarray
        Coordinate of points forming the 3D grid.
    """
    # create indices for x and y with correct spacing
    coords = []
    for dim in range(3):
        ln = grid_shape[dim]
        spacing = grid_spacing[dim]
        if ln != 1:
            coord = np.linspace(-0.5, 0.5, ln) * (ln - 1) * spacing
        else:
            coord = 0
        coords.append(coord)
    # convert to stack form (x, y, z, 3)
    grid = np.stack(np.meshgrid(*coords, indexing="ij"), axis=3)
    if squeeze:
        grid = grid.squeeze()
    return grid


def generate_2D_grid(
    grid_shape: Tuple[int, int] = (10, 10), grid_spacing: Tuple[float, float] = (1, 1)
) -> np.ndarray:
    """
    Generate a 2D sampling grid with specified shape and spacing.

    The grid generated is centered on the origin, lying on the plane with normal
    vector [0, 0, 1], has shape (m, n, 3) for grid_shape (m, n), and spacing
    grid_spacing between neighboring points.

    Parameters
    ----------
    grid_shape : Tuple[int, int]
        The number of grid points along each axis.
    grid_spacing : Tuple[float, float]
        Spacing between points in the sampling grid.

    Returns
    -------
    np.ndarray
        Coordinate of points forming the 2D grid.
    """
    return generate_3D_grid(grid_shape=(*grid_shape, 1), grid_spacing=(*grid_spacing, 1))


def generate_1D_grid(
    grid_shape: int = 10, grid_spacing: float = 1
) -> np.ndarray:
    """
    Generate a 1D sampling grid with specified shape and spacing.

    The grid generated is centered on the origin, lying along the vector
    [0, 0, 1], has shape (m, 3) for grid_shape m, and spacing grid_spacing
    between neighboring points.

    Parameters
    ----------
    grid_shape : int
        The number of grid points.
    grid_spacing : float
        Spacing between points in the sampling grid.

    Returns
    -------
    np.ndarray
        Coordinate of points forming the 1D grid.
    """
    return generate_3D_grid(grid_shape=(1, 1, grid_shape), grid_spacing=(1, 1, grid_spacing))


def generate_sampling_coordinates(
    sampling_grid: np.ndarray, positions: np.ndarray, orientations: Rotation
) -> np.ndarray:
    """
    Copy and transform a given sampling grid onto a set of positions and orientations.

    Returns a (batch, *grid_shape, 3) batch of coordinate grids for sampling.

    Parameters
    ----------
    sampling_grid : np.ndarray
        Grid of points to be copied and transformed.
    positions : np.ndarray
        Array of coordinates used to shift sampling grids.
    orientations : Rotation
        Rotations to be applied to each grid before shifts.

    Returns
    -------
    np.ndarray
        Coordinate of points combining all the transformed grids.
    """
    rotated = []
    grid_shape = sampling_grid.shape
    grid_coords = sampling_grid.reshape(-1, 3)
    # apply each orientation to the grid and store the result
    for orientation in orientations:
        rotated.append(orientation.apply(grid_coords))
    # shift each rotated
    rotated_shifted = np.stack(rotated, axis=1) + positions
    return rotated_shifted.reshape(-1, *grid_shape)


def sample_volume_at_coordinates(
    volume: np.ndarray, coordinates: np.ndarray, interpolation_order: int = 3
) -> np.ndarray:
    """
    Sample a volume with spline interpolation at specific coordinates.

    The output shape is determined by the input coordinate shape such that
    if coordinates have shape (batch, *grid_shape, 3), the output array will have
    shape (*grid_shape, batch).

    Parameters
    ----------
    volume : np.ndarray
        Volume to be sampled.
    coordinates : np.ndarray
        Array of coordinates at which to sample the volume. The shape of this array
        should be (batch, *grid_shape, 3) to allow reshaping back correctly
    interpolation_order : int
        Spline order for image interpolation.

    Returns
    -------
    np.ndarray
        Array of shape (*grid_shape)
    """
    batch, *grid_shape, _ = coordinates.shape
    # map_coordinates wants transposed coordinate array
    sampled_volume = map_coordinates(
        volume, coordinates.reshape(-1, 3).T, order=interpolation_order
    )
    # reshape back (need to invert due to previous transposition)
    # and retranspose to get batch back to the 0th dimension
    return np.swapaxes(sampled_volume.reshape(*grid_shape, batch), -1, 0)


def sample_volume_along_spline(
    volume: np.ndarray,
    spline: Union[np.ndarray, Spline3D],
    sampling_shape: Tuple[int, int] = (10, 10),
    sampling_spacing: float = 1,
    interpolation_order: int = 3,
) -> np.ndarray:
    """
    Extract planes from a volume following a spline path.

    Parameters
    ----------
    volume : np.ndarray
        Volume to be sampled.
    spline : Spline3D
        Array of points to use to generate the spline, or Spline object,
        along which to sample the volume.
    sampling_shape : Tuple[int, int]
        The number of points along each axis of the grid used for plane sampling.
    sampling_spacing : Tuple[float, float]
        Spacing between points in the sampling grid and along the spline.
    interpolation_order : int
        Spline order for image interpolation.

    Returns
    -------
    np.ndarray
        Sampled volume.
    """
    if not isinstance(spline, Spline3D):
        spline = Spline3D(points=spline)
    positions = spline._get_equidistance_spline_samples(sampling_spacing)
    orientations = spline._get_equidistance_orientations(sampling_spacing)
    grid = generate_2D_grid(grid_shape=sampling_shape, grid_spacing=sampling_spacing)
    sampling_coords = generate_sampling_coordinates(grid, positions, orientations)
    return sample_volume_at_coordinates(
        volume, sampling_coords, interpolation_order=interpolation_order
    )


def sample_subvolumes(
    volume: np.ndarray,
    positions: np.ndarray,
    orientations: Rotation,
    grid_shape: Tuple[int, int, int] = (10, 10, 10),
    grid_spacing: Tuple[float, float, float] = (1, 1, 1),
    interpolation_order: int = 3,
) -> np.ndarray:
    """
    Extract arbitrarily oriented subvolumes from a volume.

    Parameters
    ----------
    volume : np.ndarray
        Volume to be sampled.
    positions : np.ndarray
        Positions of subvolumes.
    orientations : Rotation
        Orientations of subvolumes.
    grid_shape : Tuple[int, int, int]
        Shape of the 3D grid.
    grid_spacing : Tuple[float, float, float]
        Spacing between points in the sampling grid.
    interpolation_order : int
        Spline order for image interpolation.

    Returns
    -------
    np.ndarray
        Sampled volume.
    """
    grid = generate_3D_grid(grid_shape=grid_shape, grid_spacing=grid_spacing, squeeze=False)
    sampling_coords = generate_sampling_coordinates(grid, positions, orientations)
    return sample_volume_at_coordinates(
        volume, sampling_coords, interpolation_order=interpolation_order
    )


def sample_volume_around_surface(
    volume: np.ndarray,
    surface: Union[np.ndarray, SplineSurfaceGrid],
    sampling_thickness: int,
    sampling_spacing: float,
    interpolation_order: int = 3,
) -> np.ndarray:
    """
    Sample a volume around an arbitrary surface.

    Parameters
    ----------
    volume : np.ndarray
        Volume to be sampled.
    surface : Union[np.ndarray, SplineSurfaceGrid]
        Array of points to be used to generate a surface, or SplineSurfaceGrid object,
        along which to sample the volume.
    sampling_thickness : int
        Thickness of sampled surface in pixels.
    sampling_spacing : float
        Spacing between sampled pixels.
    interpolation_order : int
        Spline order for image interpolation.

    Returns
    -------
    np.ndarray
        Sampled volume.
    """
    if not isinstance(surface, SplineSurfaceGrid):
        surface = SplineSurfaceGrid(points=surface, separation=sampling_spacing)
    grid = generate_1D_grid(grid_shape=sampling_thickness, grid_spacing=sampling_spacing)
    positions = surface.sample_surface()
    orientations = surface.sample_surface_orientations()
    sampling_coords = generate_sampling_coordinates(grid, positions, orientations)
    sampled = sample_volume_at_coordinates(volume, sampling_coords, interpolation_order=interpolation_order)
    return sampled.reshape(*surface.grid_shape, sampling_thickness)
